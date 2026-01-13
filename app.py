from flask import Flask, render_template, request, jsonify, session
import pandas as pd
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv
import os
import json
import io
import base64
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from collections import deque
import uuid
import pickle
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SESSION_FOLDER'] = 'sessions'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Increase timeouts for production
import socket
socket.setdefaulttimeout(300)  # 5 minutes timeout

# Configure Gemini API
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    genai.configure(api_key=api_key)
    logger.info("Gemini API configured successfully")
else:
    logger.error("GEMINI_API_KEY not found in environment variables")

# Get max invoices per session limit (0 = unlimited)
MAX_INVOICES_PER_SESSION = int(os.getenv('MAX_INVOICES_PER_SESSION', 0))
logger.info(f"Max invoices per session: {MAX_INVOICES_PER_SESSION if MAX_INVOICES_PER_SESSION > 0 else 'Unlimited'}")

INVOICE_SCHEMA = [
    "Invoice_Date",
    "Invoice_No",
    "Supplier_Name",
    "Supplier_NTN",
    "Supplier_GST_No",
    "Supplier_Registration_No",
    "Buyer_Name",
    "Buyer_NTN",
    "Buyer_GST_No",
    "Buyer_Registration_No",
    "Exclusive_Value",
    "GST_Sales_Tax",
    "Inclusive_Value",
    "Advance_Tax",
    "Net_Amount",
    "Discount",
    "Incentive",
    "Location"
]

# Rate Limiter Class
class RateLimiter:
    """Simple rate limiter to prevent hitting API quota"""

    def __init__(self, max_calls_per_minute=15):
        self.max_calls = max_calls_per_minute
        self.calls = deque()
        self.lock = threading.Lock()

    def wait_if_needed(self):
        """Wait if we've hit the rate limit"""
        with self.lock:
            now = time.time()

            # Remove calls older than 1 minute
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()

            # If we've hit the limit, wait
            if len(self.calls) >= self.max_calls:
                sleep_time = 60 - (now - self.calls[0]) + 1
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    # Clear old calls after waiting
                    while self.calls and time.time() - self.calls[0] > 60:
                        self.calls.popleft()

            # Record this call
            self.calls.append(time.time())

# Global rate limiter (50 calls per minute - allows parallel processing)
# Gemini 1.5 Flash free tier: 15 RPM, 1500 RPD, 1 million TPM
# Setting to 50 allows burst processing but will throttle if needed
rate_limiter = RateLimiter(max_calls_per_minute=50)

# Global storage for processed invoices with disk persistence
processed_invoices = {}
processed_invoices_lock = threading.Lock()

def save_session_to_disk(session_id, data):
    """Save session data to disk for persistence"""
    try:
        session_dir = Path(app.config['SESSION_FOLDER'])
        session_dir.mkdir(exist_ok=True)
        session_file = session_dir / f"{session_id}.pkl"
        with open(session_file, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"Session {session_id} saved to disk")
    except Exception as e:
        logger.error(f"Failed to save session {session_id}: {str(e)}")

def load_session_from_disk(session_id):
    """Load session data from disk"""
    try:
        session_file = Path(app.config['SESSION_FOLDER']) / f"{session_id}.pkl"
        if session_file.exists():
            with open(session_file, 'rb') as f:
                data = pickle.load(f)
            logger.info(f"Session {session_id} loaded from disk")
            return data
        return None
    except Exception as e:
        logger.error(f"Failed to load session {session_id}: {str(e)}")
        return None

def get_session_data(session_id):
    """Get session data from memory or disk"""
    with processed_invoices_lock:
        # Try memory first
        if session_id in processed_invoices:
            logger.info(f"Session {session_id} found in memory")
            return processed_invoices[session_id]
        
        # Try disk
        data = load_session_from_disk(session_id)
        if data:
            # Cache in memory
            processed_invoices[session_id] = data
            return data
        
        logger.warning(f"Session {session_id} not found in memory or disk")
        return None


def pdf_to_images(pdf_bytes):
    """Convert PDF bytes to list of images using PyMuPDF"""
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        pdf_document.close()
        logger.info(f"Successfully converted PDF to {len(images)} images")
        return images
    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {str(e)}")
        return []


def image_to_base64(image):
    """Convert PIL Image to base64 string"""
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return base64.b64encode(img_byte_arr.read()).decode('utf-8')


def extract_invoice_data_with_gemini(image, schema, max_retries=3):
    """Use Gemini Vision to extract invoice data with retry logic"""

    last_error = None

    for attempt in range(max_retries):
        try:
            # Apply rate limiting
            rate_limiter.wait_if_needed()

            # Convert image to base64
            img_base64 = image_to_base64(image)

            # Initialize Gemini model
            model = genai.GenerativeModel('gemini-2.5-flash')
#    random commit
            prompt = f"""
            You are an expert invoice data extractor. Analyze this invoice image carefully and extract the following information.

            Extract these fields: {', '.join(schema)}

            IMPORTANT RULES:
            1. Return ONLY a valid JSON object, nothing else
            2. Use YYYY-MM-DD format for dates
            3. Extract numbers without currency symbols or commas
            4. If a field is not found or unclear, use null
            5. Do NOT include any explanations or text outside the JSON

            Example JSON response:
            {{
                "Invoice_Date": "2024-01-15",
                "Invoice_No": "INV-12345",
                "Supplier_Name": "ABC Company",
                "Supplier_NTN": "1234567",
                "Supplier_GST_No": "GST-123",
                "Supplier_Registration_No": "REG-456",
                "Buyer_Name": "XYZ Ltd",
                "Buyer_NTN": "7654321",
                "Buyer_GST_No": "GST-789",
                "Buyer_Registration_No": "REG-012",
                "Exclusive_Value": "10000",
                "GST_Sales_Tax": "1800",
                "Inclusive_Value": "11800",
                "Advance_Tax": "200",
                "Net_Amount": "11600",
                "Discount": "500",
                "Incentive": "100",
                "Location": "Karachi, Pakistan"
            }}
            """

            # Send request to Gemini
            image_part = {
                "mime_type": "image/png",
                "data": img_base64
            }

            response = model.generate_content(
                [prompt, image_part],
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                )
            )

            if not response or not response.text:
                raise Exception("EMPTY_RESPONSE")

            response_text = response.text.strip()

            # Clean markdown code blocks
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            elif response_text.startswith('```'):
                response_text = response_text[3:]

            if response_text.endswith('```'):
                response_text = response_text[:-3]

            response_text = response_text.strip()

            # Parse JSON
            try:
                extracted_data = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to find JSON in response
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    extracted_data = json.loads(json_match.group())
                else:
                    raise Exception("INVALID_JSON")

            # Filter to only include schema fields
            filtered_data = {key: extracted_data.get(key) for key in schema}

            return filtered_data

        except Exception as e:
            error_str = str(e).lower()
            last_error = str(e)
            logger.error(f"API call failed (attempt {attempt + 1}/{max_retries}): {str(e)}")

            # Check for quota/rate limit errors
            if any(keyword in error_str for keyword in ['quota', 'rate limit', 'resource exhausted', '429']):
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                else:
                    return None

            # Retry with backoff
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            else:
                return None

    return None


def process_single_invoice(image, source_file, page_num, schema):
    """Process a single invoice"""
    try:
        extracted_data = extract_invoice_data_with_gemini(image, schema)

        if extracted_data:
            img_base64 = image_to_base64(image)
            extracted_data['Source_File'] = source_file
            extracted_data['Page_Number'] = page_num
            extracted_data['_image_base64'] = img_base64
            logger.info(f"Successfully processed {source_file} - Page {page_num}")
            return extracted_data
        else:
            logger.warning(f"Failed to extract data from {source_file} - Page {page_num}")
            return None
    except Exception as e:
        logger.error(f"Error processing {source_file} - Page {page_num}: {str(e)}")
        return None


def process_file_parallel(file_path, filename, schema, max_workers=5):
    """Process file with multi-threading"""
    results = []

    try:
        # Determine file type
        file_extension = filename.lower().split('.')[-1]

        if file_extension == 'pdf':
            with open(file_path, 'rb') as f:
                pdf_bytes = f.read()
            images = pdf_to_images(pdf_bytes)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        process_single_invoice,
                        image,
                        filename,
                        page_num,
                        schema
                    ): page_num
                    for page_num, image in enumerate(images, start=1)
                }

                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
        else:
            # Process image file
            image = Image.open(file_path)
            result = process_single_invoice(image, filename, 1, schema)
            if result:
                results.append(result)

        return results

    except Exception as e:
        logger.error(f"Error processing file {filename}: {str(e)}")
        return []


@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html', schema=INVOICE_SCHEMA, max_invoices=MAX_INVOICES_PER_SESSION)


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file upload and processing"""
    try:
        if 'files[]' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400

        files = request.files.getlist('files[]')

        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400

        # Count total invoices to process (pages in PDFs + individual images)
        total_invoice_count = 0
        for file in files:
            if file and file.filename:
                file_extension = file.filename.lower().split('.')[-1]
                if file_extension == 'pdf':
                    # Save temporarily to count pages
                    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{file.filename}")
                    file.save(temp_path)
                    with open(temp_path, 'rb') as f:
                        pdf_bytes = f.read()
                    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    total_invoice_count += len(pdf_doc)
                    pdf_doc.close()
                    os.remove(temp_path)
                    file.seek(0)  # Reset file pointer
                else:
                    total_invoice_count += 1

        # Check if exceeds limit
        if MAX_INVOICES_PER_SESSION > 0 and total_invoice_count > MAX_INVOICES_PER_SESSION:
            return jsonify({
                'error': f'Invoice limit exceeded. Maximum {MAX_INVOICES_PER_SESSION} invoices allowed per session. You attempted to process {total_invoice_count} invoices.',
                'limit': MAX_INVOICES_PER_SESSION,
                'attempted': total_invoice_count
            }), 400

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Save files and process
        all_results = []
        file_results = {}

        for file in files:
            if file and file.filename:
                # Save file temporarily
                filename = file.filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                # Process file
                results = process_file_parallel(filepath, filename, INVOICE_SCHEMA)

                if results:
                    all_results.extend(results)
                    file_results[filename] = {
                        'success': True,
                        'count': len(results)
                    }
                else:
                    file_results[filename] = {
                        'success': False,
                        'count': 0
                    }

                # Clean up file
                try:
                    os.remove(filepath)
                except:
                    pass

        # Store results in memory and disk
        with processed_invoices_lock:
            processed_invoices[session_id] = all_results
        
        # Save to disk for persistence
        save_session_to_disk(session_id, all_results)
        
        logger.info(f"Session {session_id}: Processed {len(all_results)} invoices successfully")

        return jsonify({
            'success': True,
            'session_id': session_id,
            'total_invoices': len(all_results),
            'file_results': file_results
        })

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/get_invoices/<session_id>')
def get_invoices(session_id):
    """Get processed invoices for a session"""
    logger.info(f"Fetching invoices for session: {session_id}")
    
    invoices = get_session_data(session_id)
    if invoices is None:
        logger.error(f"Session not found: {session_id}")
        return jsonify({'error': 'Session not found'}), 404

    # Prepare data for frontend (without base64 images for the table)
    table_data = []
    for idx, invoice in enumerate(invoices):
        row = {'row_id': idx}
        for field in ['Source_File', 'Page_Number'] + INVOICE_SCHEMA:
            row[field] = invoice.get(field, '')
        table_data.append(row)

    return jsonify({
        'success': True,
        'invoices': table_data
    })


@app.route('/get_invoice_image/<session_id>/<int:invoice_id>')
def get_invoice_image(session_id, invoice_id):
    """Get invoice image and data for modal"""
    logger.info(f"Fetching invoice image for session: {session_id}, invoice: {invoice_id}")
    
    invoices = get_session_data(session_id)
    if invoices is None:
        logger.error(f"Session not found: {session_id}")
        return jsonify({'error': 'Session not found'}), 404

    if invoice_id < 0 or invoice_id >= len(invoices):
        return jsonify({'error': 'Invoice not found'}), 404

    invoice = invoices[invoice_id]

    return jsonify({
        'success': True,
        'image': invoice.get('_image_base64', ''),
        'data': {k: v for k, v in invoice.items() if k != '_image_base64'}
    })


@app.route('/export/<session_id>')
def export_excel(session_id):
    """Export invoices to Excel"""
    logger.info(f"Exporting session: {session_id}")
    
    invoices = get_session_data(session_id)
    if invoices is None:
        logger.error(f"Session not found: {session_id}")
        return jsonify({'error': 'Session not found'}), 404

    # Prepare DataFrame
    df_data = []
    for invoice in invoices:
        row = {}
        for field in ['Source_File', 'Page_Number'] + INVOICE_SCHEMA:
            row[field] = invoice.get(field, '')
        df_data.append(row)

    df = pd.DataFrame(df_data)

    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Invoice Data')

    output.seek(0)

    from flask import send_file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'invoices_{timestamp}.xlsx'
    )


if __name__ == '__main__':
    # Create folders if they don't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['SESSION_FOLDER'], exist_ok=True)

    # Run app
    port = int(os.environ.get('PORT', 8080))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting server on port {port}")
    logger.info(f"Debug mode: {debug_mode}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True)
