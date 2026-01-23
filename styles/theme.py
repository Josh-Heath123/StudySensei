"""Apple-style minimalist theme CSS."""

def get_app_styles() -> str:
    """Return the complete CSS stylesheet for the app."""
    return """
    <style>
    /* Apple-style Minimalist Design */
    
    /* Base colors - light, calm palette */
    body { 
        background: #f5f5f7; 
        color: #1d1d1f; 
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
    }
    .stApp { 
        background: #f5f5f7; 
    }
    
    /* Typography - light weight, generous spacing */
    .header-title { 
        font-size: 48px; 
        font-weight: 300; 
        color: #1d1d1f; 
        text-align: center; 
        margin-bottom: 0.5rem;
        letter-spacing: -0.5px;
        line-height: 1.1;
    }
    .header-subtitle { 
        font-size: 17px; 
        font-weight: 400;
        color: #86868b; 
        text-align: center;
        margin-bottom: 3rem;
        line-height: 1.5;
    }
    
    /* Buttons - clean, subtle, single accent */
    .stButton>button { 
        width: 100%; 
        border-radius: 12px; 
        padding: 0.875rem 1.5rem; 
        font-weight: 400;
        font-size: 17px;
        border: none;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    }
    .stButton>button:active {
        transform: translateY(0);
        box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    }
    
    /* Button variants - single accent color */
    .start-btn>button { 
        background: #007AFF; 
        color: #1d1d1f; 
    }
    .start-btn>button:hover {
        background: #0051D5;
    }
    .stop-btn>button { 
        background: #f5f5f7; 
        color: #1d1d1f;
        border: 1px solid #d2d2d7;
    }
    .stop-btn>button:hover {
        background: #e8e8ed;
    }
    .toggle-btn>button { 
        background: #f5f5f7; 
        color: #1d1d1f;
        border: 1px solid #d2d2d7;
    }
    .toggle-btn>button:hover {
        background: #e8e8ed;
    }
    
    /* Card - subtle depth, no borders */
    .card { 
        background: #ffffff; 
        padding: 2rem; 
        border-radius: 18px; 
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border: none;
        margin-bottom: 2rem;
    }
    
    /* Checkboxes - clean styling with black text */
    .stCheckbox label {
        font-weight: 400;
        font-size: 15px;
        color: #1d1d1f !important;
        line-height: 1.5;
    }
    .stCheckbox label p {
        color: #1d1d1f !important;
    }
    .stCheckbox {
        color: #1d1d1f !important;
    }
    .stCheckbox > label {
        color: #1d1d1f !important;
    }
    .stCheckbox > label > div {
        color: #1d1d1f !important;
    }
    /* Override Streamlit default white text */
    div[data-testid="stCheckbox"] label {
        color: #1d1d1f !important;
    }
    div[data-testid="stCheckbox"] label p {
        color: #1d1d1f !important;
    }
    
    /* Dividers - subtle */
    hr {
        border: none;
        border-top: 0.5px solid #d2d2d7;
        margin: 2rem 0;
    }
    
    /* Info/Warning boxes - subtle */
    .stAlert {
        border-radius: 12px;
        border: none;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    
    /* Streamlit default overrides */
    .stMarkdown {
        color: #1d1d1f;
    }
    
    /* Remove default Streamlit borders */
    .element-container {
        margin-bottom: 1.5rem;
    }
    
    /* Image styling - rounded corners */
    .stImage img {
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    
    /* Smooth transitions for all interactive elements */
    * {
        transition: background-color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
                    color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
                    transform 0.2s cubic-bezier(0.4, 0, 0.2, 1),
                    box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    /* Input fields - Apple-style */
    .stTextInput>div>div>input,
    .stNumberInput>div>div>input {
        border-radius: 8px;
        border: 0.5px solid #d2d2d7;
        padding: 0.75rem 1rem;
        font-size: 15px;
    }
    
    /* Select boxes */
    .stSelectbox>div>div>select {
        border-radius: 8px;
        border: 0.5px solid #d2d2d7;
    }
    
    /* Consistent spacing throughout */
    .main .block-container {
        padding-top: 4rem;
        padding-bottom: 4rem;
        max-width: 900px;
    }
    
    /* Remove Streamlit default styling */
    .stMarkdown p {
        margin-bottom: 0.5rem;
    }
    
    /* Focus states - subtle */
    .stButton>button:focus {
        outline: none;
        box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.1);
    }
    
    /* Checkbox styling */
    .stCheckbox {
        margin-bottom: 1rem;
    }
    </style>
    """
