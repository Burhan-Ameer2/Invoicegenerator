# Invoice Data Extractor Pro ⚡

A production-ready AI-powered invoice data extraction tool with multi-threading capabilities. Built with Flask, Bootstrap 5, and Google Gemini Vision.

![Version](https://img.shields.io/badge/version-3.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![Flask](https://img.shields.io/badge/flask-3.0-red)

## ✨ Key Features

### 🎨 Professional Web Interface
- **Bootstrap 5**: Modern, responsive UI
- **DataTables.js**: Sortable, searchable table with pagination
- **Modal Popup**: Native Bootstrap modal for invoice preview
- **Drag & Drop**: Upload files by dragging or clicking
- **Real-time Progress**: Live progress bar during processing
- **Professional Design**: Gradient themes and smooth animations

### ⚡ Lightning-Fast Performance
- **Multi-Threading**: Process multiple invoices simultaneously (8 workers)
- **Parallel Processing**: Concurrent API requests to Gemini
- **Rate Limiting**: Automatic rate limiting (12 calls/minute)
- **Optimized**: Fast response times

### 📊 Advanced Data Processing
- **Multiple Formats**: PDF, PNG, JPEG, WEBP
- **Batch Processing**: Upload multiple files at once
- **Multi-Page PDF**: Each page extracted as separate invoice
- **AI Vision**: Google Gemini 1.5 Flash
- **15 Fields**: Comprehensive data extraction

### 📤 Export Options
- **Excel Export**: Download as XLSX with timestamp
- **All Data Included**: 15 fields + metadata

## 📋 Extracted Fields

| Category | Fields |
|----------|--------|
| **Invoice Info** | Invoice_Date, Invoice_No |
| **Supplier Details** | Supplier_Name, Supplier_NTN, Supplier_GST_No, Supplier_Registration_No |
| **Buyer Details** | Buyer_Name, Buyer_NTN, Buyer_GST_No, Buyer_Registration_No |
| **Financial Data** | Exclusive_Value, GST_Sales_Tax, Inclusive_Value, Advance_Tax, Net_Amount |

## 🚀 Quick Start (Local)

### Prerequisites

- Python 3.10+
- Google Gemini API key

### Installation

1. **Clone or download the project**

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure API key:**
Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_actual_api_key_here
SECRET_KEY=your-secret-key-for-flask-sessions
```

4. **Get Gemini API Key:**
   - Visit: https://makersuite.google.com/app/apikey
   - Sign in with Google account
   - Create API key
   - Copy to `.env` file

5. **Run the application:**
```bash
python app.py
```

6. **Open browser:**
   Navigate to `http://localhost:5000`

## 🌐 Deployment to Render (FREE)

### Step 1: Prepare Your Code

1. Ensure all files are in place:
   - `app.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
   - `templates/index.html`
   - `static/css/style.css`
   - `static/js/main.js`

2. Create a `.env` file (don't commit it):
```
GEMINI_API_KEY=your_api_key_here
SECRET_KEY=your-secret-key-here
```

### Step 2: Push to GitHub

```bash
# Initialize git (if not already)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Flask invoice extractor"

# Create repository on GitHub and push
git remote add origin https://github.com/YOUR_USERNAME/invoice-extractor.git
git branch -M main
git push -u origin main
```

### Step 3: Deploy on Render

1. **Go to Render:** https://render.com
2. **Sign up/Login** (use GitHub account)
3. **Create New Web Service:**
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the invoice-extractor repo

4. **Configure Service:**
   - **Name:** `invoice-extractor` (or your choice)
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** Free

5. **Add Environment Variables:**
   - Click "Environment" tab
   - Add: `GEMINI_API_KEY` = your_api_key
   - Add: `SECRET_KEY` = random_string_here

6. **Deploy:**
   - Click "Create Web Service"
   - Wait 2-5 minutes for deployment
   - Your app will be live at: `https://invoice-extractor-xxxx.onrender.com`

### Important Notes for Render:

✅ **Free Tier Limits:**
- App sleeps after 15 min inactivity (wakes in ~30 seconds)
- 750 hours/month free
- Perfect for demos and prototypes

✅ **Auto-Deploy:**
- Every git push automatically deploys
- No manual intervention needed

✅ **SSL Certificate:**
- Automatic HTTPS
- Professional URL

## 💡 Usage Guide

### Basic Workflow

1. **Upload Files**
   - Drag & drop files or click "Browse Files"
   - Supports PDF, PNG, JPEG, WEBP
   - Multiple files allowed

2. **Extract Data**
   - Click "Extract Data" button
   - Watch real-time progress bar
   - Processing happens in background

3. **Review Results**
   - Interactive table with search and sort
   - Click "View" button to see invoice image
   - Modal popup shows image + extracted data

4. **Navigate Invoices**
   - Use Previous/Next buttons in modal
   - Press ESC to close modal
   - Click outside modal to close

5. **Export**
   - Click "Download Excel"
   - Timestamped XLSX file downloads
   - All data included

## 📁 Project Structure

```
invoice-matcher/
├── app.py                      # Flask application (backend)
├── templates/
│   └── index.html             # HTML template
├── static/
│   ├── css/
│   │   └── style.css          # Custom styles
│   └── js/
│       └── main.js            # JavaScript logic
├── uploads/                    # Temporary file storage
├── requirements.txt            # Python dependencies
├── Procfile                    # Deployment config
├── runtime.txt                 # Python version
├── .env                        # Environment variables (not committed)
├── .gitignore                  # Git ignore rules
└── README_FLASK.md            # This file
```

## 🔧 Technical Details

### Stack
- **Backend:** Flask 3.0 (Python web framework)
- **Frontend:** Bootstrap 5 + jQuery
- **Table:** DataTables.js (enterprise-grade)
- **Modal:** Bootstrap Modal (native)
- **AI:** Google Gemini 1.5 Flash
- **PDF:** PyMuPDF (fitz)
- **Deployment:** Gunicorn WSGI server

### API Routes
- `GET /` - Main page
- `POST /upload` - Upload and process files
- `GET /get_invoices/<session_id>` - Get processed invoices
- `GET /get_invoice_image/<session_id>/<invoice_id>` - Get invoice details
- `GET /export/<session_id>` - Export to Excel

### Features
- Session-based storage (use database in production)
- Multi-threaded processing (8 workers)
- Automatic rate limiting (12 calls/min)
- File validation and error handling
- Base64 image encoding
- JSON API responses

## 🛠️ Troubleshooting

**Issue: "Module not found"**
- Run: `pip install -r requirements.txt`
- Ensure virtual environment activated

**Issue: "API Key Error"**
- Check `.env` file exists
- Verify `GEMINI_API_KEY` is set
- No extra spaces in API key

**Issue: "Port already in use"**
- Change port in `app.py`: `app.run(port=5001)`
- Or kill process using port 5000

**Issue: "Upload fails"**
- Check file size < 50MB
- Ensure `uploads/` folder exists
- Check file permissions

**Issue: "Modal not showing"**
- Check browser console for errors
- Ensure jQuery and Bootstrap JS loaded
- Clear browser cache

## 🌟 Production Recommendations

### For Production Use:

1. **Database:** Replace in-memory storage with PostgreSQL/MongoDB
2. **Storage:** Use S3/Cloud Storage for invoice images
3. **Queue:** Add Redis + Celery for background processing
4. **Auth:** Implement user authentication
5. **Monitoring:** Add error tracking (Sentry)
6. **Caching:** Implement Redis caching
7. **Security:** Add CSRF protection, input validation
8. **Testing:** Write unit tests and integration tests

### Scaling Options:

- **Railway:** $5/month (no sleep time)
- **DigitalOcean:** $5/month (more resources)
- **AWS/GCP:** Pay as you go (enterprise)

## 🎯 Use Cases

- **Accounting Firms:** Automate invoice processing
- **E-commerce:** Supplier invoice management
- **Finance Teams:** Data reconciliation
- **Audit:** Quick data compilation
- **SMBs:** Reduce manual entry

## 📝 Environment Variables

Required:
- `GEMINI_API_KEY` - Google Gemini API key
- `SECRET_KEY` - Flask secret key (random string)

Optional:
- `PORT` - Server port (default: 5000)

## 🤝 Demo Tips

1. Prepare 3-5 sample invoices
2. Show drag & drop functionality
3. Demonstrate real-time progress
4. Show sortable/searchable table
5. Click View button to show modal
6. Export to Excel
7. Show responsive design (mobile)

## 📄 License

Created for demonstration purposes.

## 👨‍💻 Support

For issues:
1. Check error logs in terminal
2. Verify API key is valid
3. Check Render logs (if deployed)
4. Ensure all dependencies installed

---

**Built with ❤️ using Flask, Bootstrap 5, and Google Gemini AI**

**Live Demo:** Deploy your own in 10 minutes! 🚀
