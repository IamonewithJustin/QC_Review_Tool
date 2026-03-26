"""Extract plain text from PDF and DOCX files."""

from pathlib import Path


def read_document(file_path: str) -> str:
    """
    Extract and return all text from a PDF or DOCX file.
    Raises ValueError for unsupported formats.
    Raises FileNotFoundError if the path does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _read_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Only PDF and DOCX are supported.")


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required to read PDF files. Run: pip install pdfplumber")

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx is required to read DOCX files. Run: pip install python-docx")

    doc = Document(str(path))
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
    return "\n\n".join(paragraphs)
