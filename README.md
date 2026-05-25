# Ateka Order Processing & Automation Portal ⚙️

This repository contains an advanced, automated order processing and validation tool built for B2B purchase orders. It intakes raw order files (Excel, CSV, and PDFs) from various ERP systems, extracts exact SKUs and quantities, maps them to an internal catalog, and generates a clean, validated, and formatted Excel file ready for import into the Ateka Portal.

## 🌟 Key Features

* **Hybrid PDF Processing (Native & Scanned):**
    * **Native PDFs:** Automatically detects digital PDFs and uses `PyMuPDF` to extract raw text with 100% mechanical precision, eliminating AI hallucinations or optical character recognition (OCR) errors.
    * **Scanned PDFs:** Falls back to AI Vision (`GPT-4o`) for image-based PDFs, converting pages at high-resolution (300 DPI) to ensure accurate parsing.
* **Smart Catalog Cross-Referencing:**
    * Loads the internal SKU catalog (`PB.csv`) into a fast in-memory cache using Pandas.
    * Sanitizes inputs (strips spaces, dashes, leading zeros).
    * Prioritizes internal 'Ateka' SKUs; if missing, maps 'Vendor/Manufacturer' SKUs to Ateka SKUs automatically.
    * Blocks placeholder/synthetic SKUs (e.g., `888888`) and flags unrecognized items.
* **Rigorous Data Enforcement:**
    * Enforces a strict 9-character Ateka SKU format using zero-padding (`zfill`).
    * Standardizes quantities to integers (ignoring floating points like `.00`).
* **Interactive Streamlit UI:**
    * Right-to-Left (RTL) styled interface.
    * Immediate validation feedback via color-coded alerts (Success ✅, Warning ⚠️, Error ❌).
    * Secured PDF processing requiring a password, while Excel processing remains open.
* **Production Ready:**
    * Optimized for deployment on Railway.

## 🏗️ Architecture & Flow

1.  **Input:** User uploads a `.xlsx`, `.csv`, or `.pdf` file.
2.  **Routing:**
    * *Excel/CSV* goes directly to the Python verification engine (`excel_handler.py`).
    * *PDFs* go to the Hybrid Extractor (`pdf_handler.py`). Digital text is parsed strictly; images are sent to OpenAI API via Structured Outputs (Pydantic).
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
* `pdf_handler.py`: Advanced PDF logic (Native text extraction vs. Scanned image OCR) interacting with the OpenAI API.
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
