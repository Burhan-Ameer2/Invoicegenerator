import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Mock Flask app for SQLAlchemy context
app = Flask(__name__)

# Database Configuration
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///invoice_generator.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Database Models (Must match app.py) ---

class SchemaField(db.Model):
    __tablename__ = 'schema_fields'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UsageStats(db.Model):
    __tablename__ = 'usage_stats'
    id = db.Column(db.Integer, primary_key=True)
    total_calls = db.Column(db.Integer, default=0)
    trial_start_date = db.Column(db.DateTime, default=datetime.utcnow)

# --- Seeding Logic ---

def seed_database():
    """Seed the database with initial fields and usage stats"""
    with app.app_context():
        logger.info("Starting database initialization...")
        db.create_all()
        
        # 1. Seed Schema Fields
        if SchemaField.query.count() == 0:
            logger.info("Seeding default schema fields...")
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
                field = SchemaField(name=name, description=desc)
                db.session.add(field)
            
            db.session.commit()
            logger.info(f"Successfully seeded {len(initial_fields)} fields.")
        else:
            logger.info("Schema fields already exist, skipping...")

        # 2. Seed Usage Stats
        if UsageStats.query.count() == 0:
            logger.info("Initializing usage statistics...")
            db.session.add(UsageStats())
            db.session.commit()
            logger.info("Usage statistics initialized.")
        else:
            logger.info("Usage statistics already exist, skipping...")

        logger.info("Database seeding complete!")

if __name__ == "__main__":
    seed_database()
