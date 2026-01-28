from flask import Flask, render_template, request, jsonify, session
import pandas as pd
import fitz  # PyMuPDF
import random
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv
import os
import json
import io
import base64
import re
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from collections import deque
import uuid
import pickle
from pathlib import Path
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from types import SimpleNamespace

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

# Database Configuration
# Default to SQLite if DATABASE_URL is not provided
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    # SQLAlchemy 1.4+ requires 'postgresql://' instead of 'postgres://'
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///invoice_generator.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Model
class SchemaField(db.Model):
    __tablename__ = 'schema_fields'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or "",
            'is_active': self.is_active
        }

class UsageStats(db.Model):
    __tablename__ = 'usage_stats'
    id = db.Column(db.Integer, primary_key=True)
    total_calls = db.Column(db.Integer, default=0)
    trial_start_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'total_calls': self.total_calls,
            'trial_start_date': self.trial_start_date.isoformat(),
            'trial_expires_at': (self.trial_start_date + timedelta(days=7)).isoformat(),
            'trial_days_remaining': max(0, 7 - (datetime.utcnow() - self.trial_start_date).days),
            'is_trial_expired': (datetime.utcnow() - self.trial_start_date).days >= 7,
            'max_trial_invoices': MAX_TRIAL_INVOICES,
            'invoices_remaining': max(0, MAX_TRIAL_INVOICES - self.total_calls),
            'is_limit_reached': self.total_calls >= MAX_TRIAL_INVOICES
        }

# Initialize Database and Seed Data
def init_db():
    with app.app_context():
        db.create_all()
        # Seed initial data if table is empty
        if SchemaField.query.count() == 0:
            initial_fields = [
                ("Invoice_Date", "The date mentioned on the invoice in YYYY-MM-DD format"),
                ("Invoice_No", "The unique invoice number or reference number"),
                ("Supplier_Name", "The name of the company or person providing the goods or service"),
                ("Supplier_NTN", "National Tax Number of the supplier"),
                ("Supplier_GST_No", "GST Registration Number of the supplier (often labeled as STRN or G.S.T)"),
                ("Supplier_Registration_No", "Company registration number or STRN of the supplier"),
                ("Buyer_Name", "The name of the customer or recipient"),
                ("Buyer_NTN", "National Tax Number of the buyer"),
                ("Buyer_GST_No", "GST Registration Number of the buyer (often labeled as STRN or G.S.T)"),
                ("Buyer_Registration_No", "Company registration number or STRN of the buyer"),
                ("Exclusive_Value", "The base amount before taxes"),
                ("GST_Sales_Tax", "The amount of Sales Tax or GST applied"),
                ("Inclusive_Value", "The total amount including taxes"),
                ("Advance_Tax", "Any withholding or advance tax mentioned"),
                ("Net_Amount", "The final payable amount"),
                ("Discount", "Total discount amount applied"),
                ("Incentive", "Any incentive or bonus mentioned"),
                ("Location", "Physical location or city mentioned on the invoice")
            ]
            for name, desc in initial_fields:
                db.session.add(SchemaField(name=name, description=desc))
            db.session.commit()
            logger.info("Database seeded with initial schema fields")
        
        # Seed UsageStats if empty
        if UsageStats.query.count() == 0:
            db.session.add(UsageStats())
            db.session.commit()
            logger.info("Usage statistics initialized")

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

# Get max trial invoices limit
MAX_TRIAL_INVOICES = int(os.getenv('MAX_TRIAL_INVOICES', 1000))
logger.info(f"Max trial invoices: {MAX_TRIAL_INVOICES}")

# INVOICE_SCHEMA is now dynamic and stored in the database
def get_current_fields():
    """Fetch active fields from database"""
    return SchemaField.query.filter_by(is_active=True).all()

def get_current_schema_names():
    """Fetch active field names as a list of strings"""
    return [field.name for field in get_current_fields()]

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

# Global storage for background processing status
processing_status = {}
processing_status_lock = threading.Lock()

def get_gemini_prompt(fields):
    """Generate the Gemini prompt based on database fields with confidence scoring"""
    field_descriptions = "\n".join([f"- {f.name}: {f.description or 'Extract this value'}" for f in fields])
    
    # Static part of the prompt
    rules = """
        IMPORTANT RULES:
1. PRIORITY FOR HANDWRITTEN/MANUAL ADJUSTMENTS: Handwritten values ALWAYS take priority over printed/typed values. This includes:
   - Handwritten numbers written ABOVE, BELOW, or BESIDE printed values (use the handwritten one)
   - Handwritten totals, amounts, or corrections anywhere on the invoice
   - Manual adjustments even if the original printed value is NOT crossed out
   - Strikethrough text with handwritten replacement
   - Values written in pen/marker over or near printed numbers
   - Annotations, adjustments, or corrections in margins or empty spaces
   - Whiteout/correction fluid with new values written on top
   If you see BOTH a printed value AND a handwritten value for the same field, ALWAYS use the handwritten one - it represents the final corrected/adjusted amount.

2. Return ONLY a valid JSON object, nothing else
3. Use YYYY-MM-DD format for dates
4. Extract numbers without currency symbols or commas
5. If a field is not found or unclear, use null for value and 0 for confidence

6. AGGREGATE RELATED FIELDS: While you should extract values as they appear, if there are multiple separate line items for the SAME category (like multiple discounts, returns, or adjustments both handwritten and printed), SUM them up into the single appropriate schema field (e.g., 'Discount').

7. HANDLE RETURN/CREDIT FIELDS: Recognize handwritten or printed 'ret', 'return', 'short', 'shortage', or 'credit' as items that represent deductions. Map these to the Return or Discount field as appropriate.

8. NUMERIC FORMATS: Interpret numbers in parentheses like (123.45) as potentially negative or credit values if the schema field implies a deduction (like Discount/Return). Also recognize that handwritten values ending in '/-' (e.g., 1600/-) are numeric total amounts.

9. PRIORITY FOR EXPLICIT HANDWRITTEN LABELS: If you see handwritten text that explicitly labels a value (e.g., 'Total = 343400/-' or 'Return = 1600/-'), this EXPLICIT label-value pair takes absolute priority over any printed data or other inferred values.

10. NUMERIC ID PRECISION (NTN, STRN, GST): Extract these IDs as LITERAL STRINGS with absolute precision. 
   - DO NOT strip leading zeros (e.g., '0300...' MUST keep the leading '0').
   - DO NOT skip or group digits. Count them: STRN is typically exactly 13 digits.
   - Extract EVERY digit one-by-one. If you see '03-00-99999-56-46', read it as '0300999995646'.
   - EXAMPLE: STRN-0300999995646 means Supplier_Registration_No = "0300999995646" (exactly 13 digits with five 9s)

11. IDENTICAL DIGIT SEQUENCES: For sequences of identical digits (like '99999' or '00000'), COUNT EACH DIGIT INDIVIDUALLY. Do not estimate. The number 99999 has FIVE 9s, not four. Read: nine-nine-nine-nine-nine. Verify your extracted string has the exact same length as the original.

12. ID FIELD IDENTIFICATION: Look for labels like 'STRN', 'NTN', 'G.S.T', or 'Sales Tax Reg No'. Map these to the registration fields even if the labels vary.

13. ANTI-HALLUCINATION: Strictly extract ONLY what is explicitly visible. If a value is missing or illegible, use null. Never guess or infer values.

14. LANGUAGE PRESERVATION: Extract text in ORIGINAL language/script (e.g., Urdu, Arabic). Do NOT translate or transliterate.

15. Do NOT include any explanations or text outside the JSON

AUDITING & CONSISTENCY:
16. MATHEMATICAL CROSS-CHECK: Internally verify your extraction by checking if (Exclusive_Value + GST_Sales_Tax - Discount - Incentive) equals the final Net_Amount. If it doesn't match, re-scan the invoice for additional handwritten adjustments, deductions (like 'less short'), or corrections that you might have missed. 

17. AGGREGATE ADJUSTMENTS: If an invoice has a percentage discount (e.g., 'less 20%') AND a separate adjustment (e.g., 'less short'), SUM BOTH into the 'Discount' field to ensure the final total is mathematically correct.

=== CRITICAL BLUR DETECTION & CONFIDENCE RULES ===

18. **TWO-PHASE APPROACH - VALUE EXTRACTION vs CONFIDENCE SCORING**:
   
   **PHASE 1 - VALUE EXTRACTION** (Be thorough and extract what you see):
   - Extract the value that appears on the invoice, even if slightly blurry
   - Use context clues, mathematical relationships, and invoice structure to determine the correct value
   - Apply all the priority rules (handwritten over printed, aggregation, etc.)
   - Extract the most likely correct value based on all available evidence
   
   **PHASE 2 - CONFIDENCE SCORING** (Be strict about image quality):
   - AFTER extracting the value, separately assess the visual clarity
   - Confidence score reflects ONLY the image quality of that specific field
   - Even if you're certain of the value (from context), if it's blurry → low confidence

19. **CONFIDENCE SCORING BASED ON VISUAL CLARITY ONLY**:

   **90-100% confidence** - Only if:
   - Every character has sharp, crisp edges
   - Zero blur or pixelation
   - Perfect clarity on all characters
   
   **70-89% confidence** - Only if:
   - Text is clear and readable with minor printing artifacts
   - All characters are distinguishable
   - Slight imperfections but no actual blur
   
   **50-69% confidence** - Only if:
   - Text is readable but shows some softness
   - Characters are distinguishable but not perfectly sharp
   - Minor blur but structure is clear
   
   **30-49% confidence** - If:
   - Noticeable blur on multiple characters
   - Text is somewhat fuzzy but you can make out the value
   - Using context/pattern recognition to assist reading
   
   **0-29% confidence** - If:
   - Severe blur or pixelation
   - Heavy compression artifacts
   - Characters are very difficult to distinguish
   - Significant uncertainty about individual characters

20. **BLUR INDICATORS - CONFIDENCE ADJUSTMENTS**:
   If you observe these visual issues, reduce confidence accordingly:
   - Fuzzy/soft edges → confidence MAX 50%
   - Noticeable pixelation → confidence MAX 40%
   - JPEG compression artifacts → confidence MAX 40%
   - Characters bleeding or smudged → confidence MAX 35%
   - Severe blur where you're pattern-matching → confidence MAX 25%

21. **ANTI-PATTERN-RECOGNITION WARNING**:
   If you recognize a word/number by its overall shape but individual characters are blurry:
   - STILL extract the value (you're probably correct)
   - BUT set confidence ≤ 40% (reflects actual image quality)
   
   Example: You see blurry text that looks like "INVOICE"
   - value: "INVOICE" (extract it)
   - confidence: 30 (because it's blurry)
   - visual_clarity: "Slightly Blurry"

22. **VISUAL CLARITY FIELD** (Mandatory):
   Rate the visual quality of each field:
   - "Crisp" → Sharp, clear text
   - "Readable" → Clear enough to read without strain
   - "Slightly Blurry" → Some blur but recognizable
   - "Very Blurry/Pixelated" → Significant quality issues
   - "Missing" → Field not present

23. **VISUAL EVIDENCE** (Required if confidence > 50%):
   Describe what makes you confident:
   - For crisp text: "Sharp edges on all characters, clear serifs on T"
   - For readable text: "All digits clearly distinguishable, minor print artifacts"
   - For blurry text with >50% confidence: "Text is soft but all characters identifiable"

24. **MATHEMATICAL CONSISTENCY HELPS VALUE, NOT CONFIDENCE**:
   - If a blurry number mathematically fits the invoice total → extract that value
   - BUT still score confidence low based on the blur
   - Mathematical validation helps you extract the RIGHT value, but doesn't change the fact that the source is blurry

25. **PRACTICAL EXAMPLES**:

   Example 1: Blurry total amount
   - The number is blurry but matches the sum of line items
   - value: "15000" (extract it, math confirms it)
   - confidence: 35 (it's blurry)
   - visual_clarity: "Slightly Blurry"
   - visual_evidence: "Characters are soft but recognizable, math validation supports value"
   
   Example 2: Clear printed text
   - Sharp, crisp printing
   - value: "ACME Corporation"
   - confidence: 95 (perfectly clear)
   - visual_clarity: "Crisp"
   - visual_evidence: "All characters have sharp edges, clear spacing"
   
   Example 3: Severely pixelated date
   - Date is very blurry but format suggests 2024-01-15
   - value: "2024-01-15" (extract best guess)
   - confidence: 20 (severe pixelation)
   - visual_clarity: "Very Blurry/Pixelated"
   - visual_evidence: "Heavy pixelation, relying on date format pattern"

26. **KEY PRINCIPLE**:
   ✓ Extract the CORRECT value (use all context and rules)
   ✓ Score confidence based ONLY on visual clarity
   ✓ Be thorough in extraction, strict in confidence scoring

27. **JSON STRUCTURE**:
```json
   {
     "field_name": {
       "value": "extracted_value_or_null",
       "confidence": 0-100,
       "visual_clarity": "Crisp|Readable|Slightly Blurry|Very Blurry/Pixelated|Missing",
       "visual_evidence": "Description of visual quality and what you can see"
     }
   }
```

=== END CRITICAL BLUR DETECTION RULES ===

REMEMBER: 
- Extract values thoroughly and accurately using all available information
- Score confidence strictly based on image quality alone
- A correct value from a blurry source still gets low confidence
- Your job is to extract the RIGHT value AND honestly report how clear it was to read
            """
    
    # Build example with confidence structure
    example_fields = fields[:2] if len(fields) >= 2 else fields
    example_json = {f.name: {"value": "extracted_value", "confidence": 95, "visual_clarity": "Crisp", "visual_evidence": "Sharp edges on all letters"} for f in example_fields}
    if not example_json: 
        example_json = {"Field_Name": {"value": "extracted_value", "confidence": 95, "visual_clarity": "Crisp", "visual_evidence": "Sharp edges"}}

    return f"""
            You are an expert invoice data extractor. Analyze this invoice image carefully and extract the following information WITH confidence scores and specific visual evidence.

            Extract these fields:
            {field_descriptions} 

            {rules}

            REQUIRED JSON response format (use this exact structure):
            {json.dumps(example_json, indent=12)}
            
            Each field MUST have "value", "confidence" (0-100), "visual_clarity", and "visual_evidence" keys.
            """
    
    # Build example with confidence structure
    example_fields = fields[:2] if len(fields) >= 2 else fields
    example_json = {f.name: {"value": "extracted_value", "confidence": 95, "visual_clarity": "Crisp"} for f in example_fields}
    if not example_json: 
        example_json = {"Field_Name": {"value": "extracted_value", "confidence": 95, "visual_clarity": "Crisp"}}

    return f"""
            You are an expert invoice data extractor. Analyze this invoice image carefully and extract the following information WITH confidence scores and visual clarity assessments.

            Extract these fields:
            {field_descriptions} 

            {rules}

            REQUIRED JSON response format (use this exact structure):
            {json.dumps(example_json, indent=12)}
            
            Each field MUST have "value", "confidence" (0-100), and "visual_clarity" keys.
            """

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


def extract_invoice_data_with_gemini(image, schema, max_retries=5):
    """Use Gemini Vision to extract invoice data with confidence scores and retry logic"""

    last_error = None

    for attempt in range(max_retries):
        try:
            # Apply rate limiting
            rate_limiter.wait_if_needed()

            # Convert image to base64
            img_base64 = image_to_base64(image)

            # Initialize Gemini model
            model = genai.GenerativeModel('gemini-2.5-flash') # Using flash for better speed
            
            prompt = get_gemini_prompt(schema)

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

            # Process the new confidence format: {"field": {"value": x, "confidence": y}}
            filtered_data = {}
            confidence_scores = {}
            
            for field in schema:
                field_data = extracted_data.get(field.name)
                
                if field_data is None:
                    # Field not present
                    filtered_data[field.name] = None
                    confidence_scores[field.name] = 0
                elif isinstance(field_data, dict) and 'value' in field_data:
                    # New format with confidence, visual clarity, and evidence
                    val = field_data.get('value')
                    conf = field_data.get('confidence', 0)
                    clarity = str(field_data.get('visual_clarity', 'Crisp')).lower()
                    evidence = str(field_data.get('visual_evidence', '')).lower()
                    
                    # PHASE 5 STRICT ENFORCEMENT
                    # 1. Check clarity cap
                    if "blurry" in clarity or "pixelated" in clarity:
                        if "very" in clarity:
                            conf = min(conf, 20)
                        else:
                            conf = min(conf, 40)
                    
                    # 2. Check evidence quality
                    generic_evidence = ["looks", "okay", "good", "readable", "crisp", "clear"]
                    is_generic = all(word in generic_evidence for word in evidence.split()) or len(evidence) < 10
                    
                    if conf > 50 and is_generic:
                        logger.warning(f"Downgrading confidence for {field.name} due to generic evidence: '{evidence}'")
                        conf = 35 # Penalize lack of specific detail
                    
                    if val is None or val == "":
                        conf = 0
                    
                    filtered_data[field.name] = val
                    confidence_scores[field.name] = conf
                else:
                    # Fallback
                    filtered_data[field.name] = field_data
                    confidence_scores[field.name] = 75 
            
            # Calculate overall confidence score (average of all fields with values)
            valid_scores = [score for fname, score in confidence_scores.items() 
                          if filtered_data.get(fname) is not None]
            overall_confidence = round(sum(valid_scores) / len(valid_scores)) if valid_scores else 0
            
            # Store confidence data in the result
            filtered_data['_confidence_scores'] = confidence_scores
            filtered_data['_overall_confidence'] = overall_confidence
            
            logger.info(f"Extraction complete with overall confidence: {overall_confidence}%")
            return filtered_data

        except Exception as e:
            error_str = str(e).lower()
            last_error = str(e)
            logger.error(f"API call failed (attempt {attempt + 1}/{max_retries}): {str(e)}")

            # Check for quota/rate limit errors
            if any(keyword in error_str for keyword in ['quota', 'rate limit', 'resource exhausted', '429']):
                if attempt < max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s, 16s, 32s...
                    base_delay = 2 * (2 ** attempt)
                    # Add jitter: +/- 500ms
                    jitter = random.uniform(0, 1)
                    sleep_time = base_delay + jitter
                    
                    logger.warning(f"Rate limit hit. Sleeping for {sleep_time:.2f}s before retry.")
                    time.sleep(sleep_time)
                    continue
                else:
                    return None

            # Retry with milder backoff for other errors
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            else:
                return None

    return None


def process_single_invoice(image, source_file, page_num, schema, session_id=None):
    """Process a single invoice"""
    try:
        extracted_data = extract_invoice_data_with_gemini(image, schema)

        if extracted_data:
            img_base64 = image_to_base64(image)
            extracted_data['Source_File'] = source_file
            extracted_data['Page_Number'] = page_num
            extracted_data['_image_base64'] = img_base64
            logger.info(f"Successfully processed {source_file} - Page {page_num}")
            
            # Update progress status if session_id is provided
            if session_id:
                with processing_status_lock:
                    if session_id in processing_status:
                        processing_status[session_id]['processed'] += 1
                        # Update percentage (assuming 20-100 range for processing)
                        total = processing_status[session_id]['total']
                        processed = processing_status[session_id]['processed']
                        if total > 0:
                            # 20% for upload, 80% for processing
                            percentage = 20 + int((processed / total) * 80)
                            processing_status[session_id]['percentage'] = min(100, percentage)
                            processing_status[session_id]['message'] = f"Processing invoice {processed} of {total}..."

            return extracted_data
        else:
            logger.warning(f"Failed to extract data from {source_file} - Page {page_num}")
            if session_id:
                with processing_status_lock:
                    if session_id in processing_status:
                        processing_status[session_id]['processed'] += 1 # Still count it even if it failed
            return None
    except Exception as e:
        logger.error(f"Error processing {source_file} - Page {page_num}: {str(e)}")
        if session_id:
            with processing_status_lock:
                if session_id in processing_status:
                    processing_status[session_id]['processed'] += 1
        return None


def process_file_parallel(file_path, filename, schema, session_id=None, max_workers=5):
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
                        schema,
                        session_id
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
            result = process_single_invoice(image, filename, 1, schema, session_id)
            if result:
                results.append(result)

        return results

    except Exception as e:
        logger.error(f"Error processing file {filename}: {str(e)}")
        return []
        
# Usage API
@app.route('/api/usage', methods=['GET'])
def get_usage():
    """Get current usage statistics"""
    stats = UsageStats.query.first()
    if not stats:
        return jsonify({'error': 'Usage statistics not found'}), 404
    return jsonify(stats.to_dict())

@app.route('/api/progress/<session_id>', methods=['GET'])
def get_processing_progress(session_id):
    """Get processing progress for a session"""
    with processing_status_lock:
        status = processing_status.get(session_id)
        if not status:
            return jsonify({'error': 'Session not found'}), 404
        return jsonify(status)

@app.route('/')
def index():
    """Render main page"""
    fields = get_current_fields()
    schema_names = [f.name for f in fields]
    return render_template('index.html', schema=schema_names, max_invoices=MAX_INVOICES_PER_SESSION)


@app.route('/api/fields', methods=['GET'])
def get_fields():
    """API endpoint to get all fields"""
    fields = SchemaField.query.order_by(SchemaField.created_at).all()
    return jsonify([f.to_dict() for f in fields])

@app.route('/api/prompt-preview', methods=['GET'])
def preview_prompt():
    """API endpoint to preview the actual Gemini prompt with current fields"""
    try:
        fields = get_current_fields()
        prompt = get_gemini_prompt(fields)
        return jsonify({'prompt': prompt})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fields', methods=['POST'])
def add_field():
    """API endpoint to add a new field"""
    data = request.json
    name = data.get('name', '').strip().replace(' ', '_')
    description = data.get('description', '').strip()
    
    if not name:
        return jsonify({'error': 'Field name is required'}), 400
        
    if SchemaField.query.filter_by(name=name).first():
        return jsonify({'error': f'Field "{name}" already exists'}), 400
        
    new_field = SchemaField(name=name, description=description)
    db.session.add(new_field)
    db.session.commit()
    return jsonify(new_field.to_dict()), 201


@app.route('/api/fields/<int:field_id>', methods=['PATCH'])
def update_field(field_id):
    """API endpoint to update a field"""
    field = SchemaField.query.get_or_404(field_id)
    data = request.json
    
    if 'name' in data:
        name = data['name'].strip().replace(' ', '_')
        if name and name != field.name:
            if SchemaField.query.filter_by(name=name).first():
                return jsonify({'error': f'Field "{name}" already exists'}), 400
            field.name = name
            
    if 'description' in data:
        field.description = data['description'].strip()
        
    if 'is_active' in data:
        field.is_active = bool(data['is_active'])
        
    db.session.commit()
    return jsonify(field.to_dict())


@app.route('/api/fields/<int:field_id>', methods=['DELETE'])
def delete_field(field_id):
    """API endpoint to delete a field"""
    field = SchemaField.query.get_or_404(field_id)
    db.session.delete(field)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/prompt-preview', methods=['GET'])
def prompt_preview():
    """API endpoint to preview the AI prompt"""
    fields = get_current_fields()
    prompt = get_gemini_prompt(fields)
    return jsonify({'prompt': prompt.strip()})


@app.route('/update_schema', methods=['POST'])
def update_schema_session():
    """Legacy endpoint for backward compatibility (updates session then syncs to DB)"""
    # This now basically does nothing but keep existing JS working if needed
    # But we want to move towards the new /api/fields
    return jsonify({'success': True, 'message': 'Please use /api/fields for permanent changes'})


def check_usage_limits():
    """Check if the trial has expired or limit reached"""
    stats = UsageStats.query.first()
    if not stats:
        return True, None
    
    # Check trial expiration (7 days)
    if (datetime.utcnow() - stats.trial_start_date).days >= 7:
        return False, "Your 7-day trial has expired. The application is now unusable."
        
    # Check invoice limit
    if stats.total_calls >= MAX_TRIAL_INVOICES:
        return False, f"You have reached the maximum limit of {MAX_TRIAL_INVOICES} invoices for the trial period."

    return True, None


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file upload and start background processing"""
    try:
        # Check usage limits first
        is_allowed, error_msg = check_usage_limits()
        if not is_allowed:
            return jsonify({'error': error_msg}), 403

        if 'files[]' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400

        files = request.files.getlist('files[]')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400

        # Save files to temp paths first
        saved_files = []
        total_invoice_count = 0
        
        for file in files:
            if file and file.filename:
                temp_filename = f"temp_{uuid.uuid4()}_{file.filename}"
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
                file.save(temp_path)
                
                # Count invoices
                file_extension = file.filename.lower().split('.')[-1]
                if file_extension == 'pdf':
                    try:
                        pdf_doc = fitz.open(temp_path)
                        total_invoice_count += len(pdf_doc)
                        pdf_doc.close()
                    except Exception as e:
                        logger.error(f"Error opening PDF {file.filename}: {str(e)}")
                else:
                    total_invoice_count += 1
                
                saved_files.append((temp_path, file.filename))

        if MAX_INVOICES_PER_SESSION > 0 and total_invoice_count > MAX_INVOICES_PER_SESSION:
            # Clean up temp files
            for path, _ in saved_files:
                try: os.remove(path)
                except: pass
            return jsonify({'error': f'Limit exceeded. Max {MAX_INVOICES_PER_SESSION} allowed.'}), 400

        session_id = str(uuid.uuid4())
        
        # Initialize processing status
        with processing_status_lock:
            processing_status[session_id] = {
                'percentage': 20, # Started after upload
                'processed': 0,
                'total': total_invoice_count,
                'message': 'Starting extraction...',
                'completed': False
            }

        # Start background processing
        def run_background_processing(sid, files_to_process):
            with app.app_context():
                try:
                    all_results = []
                    current_schema_objects = get_current_fields()
                    
                    # Convert to simple objects to avoid "Working outside of application context" 
                    # errors in threads when accessing SQLAlchemy objects
                    safe_schema_objects = [
                        SimpleNamespace(name=f.name, description=f.description) 
                        for f in current_schema_objects
                    ]
                    
                    # Use ThreadPoolExecutor for parallel file processing
                    # We use max_workers=5 to match the page processing limit
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        # Submit all file processing tasks
                        future_to_file = {
                            executor.submit(
                                process_file_parallel, 
                                filepath, 
                                original_filename, 
                                safe_schema_objects, 
                                sid
                            ): (filepath, original_filename)
                            for filepath, original_filename in files_to_process
                        }

                        # Collect results as they complete
                        for future in as_completed(future_to_file):
                            filepath, original_filename = future_to_file[future]
                            try:
                                results = future.result()
                                if results:
                                    all_results.extend(results)
                                    
                                    # Increment total calls in database
                                    # This runs in the main background thread, so it's safe to use db.session
                                    stats = UsageStats.query.first()
                                    if stats:
                                        stats.total_calls += len(results)
                                        db.session.commit()
                            except Exception as e:
                                logger.error(f"Error processing file {original_filename}: {str(e)}")
                            finally:
                                # Clean up temp file immediately after processing
                                try: os.remove(filepath)
                                except: pass

                    with processed_invoices_lock:
                        processed_invoices[sid] = all_results
                    
                    save_session_to_disk(sid, all_results)
                    
                    with processing_status_lock:
                        if sid in processing_status:
                            processing_status[sid]['completed'] = True
                            processing_status[sid]['percentage'] = 100
                            processing_status[sid]['message'] = 'Processing complete!'
                            
                except Exception as e:
                    logger.error(f"Background processing error: {str(e)}")
                    with processing_status_lock:
                        if sid in processing_status:
                            processing_status[sid]['error'] = str(e)
                            processing_status[sid]['completed'] = True

        # Run in thread
        import threading
        thread = threading.Thread(target=run_background_processing, args=(session_id, saved_files))
        thread.daemon = True # Ensure thread doesn't block shutdown
        thread.start()

        return jsonify({
            'success': True, 
            'session_id': session_id, 
            'total_invoices': total_invoice_count
        })

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/get_invoices/<session_id>')
def get_invoices(session_id):
    """Get processed invoices for a session with confidence scores"""
    invoices = get_session_data(session_id)
    if invoices is None:
        return jsonify({'error': 'Session not found'}), 404

    current_schema_names = get_current_schema_names()
    table_data = []
    for idx, invoice in enumerate(invoices):
        row = {'row_id': idx}
        for field in ['Source_File', 'Page_Number'] + current_schema_names:
            row[field] = invoice.get(field, '')
        # Add overall confidence score
        row['_overall_confidence'] = invoice.get('_overall_confidence', 0)
        table_data.append(row)

    return jsonify({'success': True, 'invoices': table_data})


@app.route('/get_invoice_image/<session_id>/<int:invoice_id>')
def get_invoice_image(session_id, invoice_id):
    """Get invoice image and data for modal with confidence scores"""
    invoices = get_session_data(session_id)
    if invoices is None or invoice_id < 0 or invoice_id >= len(invoices):
        return jsonify({'error': 'Not found'}), 404

    invoice = invoices[invoice_id]
    
    # Separate internal fields from display data
    internal_fields = ['_image_base64', '_confidence_scores', '_overall_confidence']
    display_data = {k: v for k, v in invoice.items() if k not in internal_fields}
    
    return jsonify({
        'success': True,
        'image': invoice.get('_image_base64', ''),
        'data': display_data,
        'confidence_scores': invoice.get('_confidence_scores', {}),
        'overall_confidence': invoice.get('_overall_confidence', 0)
    })


@app.route('/export/<session_id>')
def export_excel(session_id):
    """Export invoices to Excel"""
    invoices = get_session_data(session_id)
    if invoices is None:
        return jsonify({'error': 'Session not found'}), 404

    current_schema_names = get_current_schema_names()
    df_data = []
    for invoice in invoices:
        row = {}
        for field in ['Source_File', 'Page_Number'] + current_schema_names:
            row[field] = invoice.get(field, '')
        df_data.append(row)

    df = pd.DataFrame(df_data)
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
    # Initialize database
    init_db()
    
    # Create folders
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['SESSION_FOLDER'], exist_ok=True)

    # Run app
    port = int(os.environ.get('PORT', 8080))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True)
