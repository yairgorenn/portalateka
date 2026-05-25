# Ateka Order Processing & Automation Portal ⚙️

This repository contains an advanced, automated order processing and validation tool built for B2B purchase orders. It intakes raw order files (Excel, CSV, and Native PDFs) from various ERP systems, extracts exact SKUs and quantities, maps them to an internal catalog, and generates a clean, validated, and formatted Excel file ready for import into the Ateka Portal.

## 🌟 Key Features

* **Zero-Hallucination Native PDF Parsing:**
    * Automatically detects and extracts raw text from digital/native PDFs using `PyMuPDF` with 100% mechanical precision. 
    * Eliminates AI hallucinations, OCR errors, and synthetic data generation by passing pure text to the AI for structuring.
* **Strict Image/Scan Blocking (Quality Control):**
    * Actively detects if a user uploads a scanned PDF or image (where text cannot be extracted deterministically).
    * Blocks the upload and prompts the user to provide a native ERP-generated PDF to ensure absolute data integrity.
* **Smart Catalog Cross-Referencing:**
    * Loads the internal SKU catalog (`PB.csv`) into a fast in-memory cache using Pandas.
    * Sanitizes inputs (strips spaces, dashes, leading zeros).
    * Prioritizes internal 'Ateka' SKUs; if missing, maps 'Vendor/Manufacturer' SKUs to Ateka SKUs automatically.
    * Blocks placeholder/synthetic SKUs (e.g., `888888`) and flags unrecognized items.
* **Rigorous Data Enforcement:**
    * Enforces a strict 9-character Ateka SKU format using zero-padding (`zfill`).
    * Implements strict Pydantic parsing rules for AI outputs to ensure quantities are always returned as pure integers (ignoring string artifacts like 'pcs' or floating points).
* **Interactive Streamlit UI:**
    * Right-to-Left (RTL) styled interface.
    * Immediate validation feedback via color-coded alerts (Success ✅, Warning ⚠️, Error ❌).
    * Secured PDF processing requiring a password, while Excel processing remains open.
* **Production Ready:**
    * Optimized for deployment on Railway with automatic environment variable handling.

## 🏗️ Architecture & Flow

1.  **Input:** User uploads a `.xlsx`, `.csv`, or `.pdf` file.
2.  **Routing & Extraction:**
    * *Excel/CSV* goes directly to the Python verification engine (`excel_handler.py`).
    * *PDFs* are analyzed by `pdf_handler.py`. If it's a native PDF, the text is extracted and structured via OpenAI API (using strict Pydantic schemas). If it's a scan, the process halts with a `SCANNED_PDF_BLOCKED` error.
3.  **Validation Engine:** The parsed SKU list is run against the cached `PB.csv` catalog to determine the valid Ateka SKU.
4.  **Output:** A dynamically formatted `.xlsx` file (`openpyxl`) is generated in-memory and offered for download.

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Web Framework:** Streamlit
* **Data Handling:** Pandas
* **Excel Generation:** openpyxl
* **PDF Processing:** PyMuPDF (`fitz`)
* **AI Engine:** OpenAI API (`gpt-4o`) with Structured Outputs (Pydantic)

## 📂 File Structure

* `app.py`: Main Streamlit application and UI routing.
* `excel_handler.py`: Core logic for caching the catalog, validating SKUs, standardizing quantities, and generating the final Excel file.
* `pdf_handler.py`: Native text extraction logic interacting with the OpenAI API for structuring, including the anti-scan safety block.
* `PB.csv`: The internal database mapping Vendor SKUs to Ateka SKUs (Not tracked/uploaded if sensitive).
* `requirements.txt`: Python dependencies.

## 🚀 Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/ateka-order-portal.git
    cd ateka-order-portal
    ```

2.  **Create a Virtual Environment & Install Dependencies:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Environment Variables:**
    Create a `.env` file or export the following variable:
    ```bash
    OPENAI_API_KEY=sk-your-openai-api-key
    ```

4.  **Run the App:**
    ```bash
    streamlit run app.py
    ```

## ☁️ Deployment (Railway)

1. Connect your GitHub repository to Railway.
2. In the Railway dashboard, navigate to the `Variables` tab.
3. Add `OPENAI_API_KEY` with your secret key.
4. Railway will automatically build and deploy the Streamlit container based on `requirements.txt`.
