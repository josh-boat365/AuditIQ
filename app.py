from flask import Flask, render_template, request, jsonify, send_file
from io import BytesIO
from docx import Document
import logging
import json
import requests
import matplotlib.pyplot as plt
from datetime import datetime
import os
import platform
import subprocess
from typing import Dict, Any

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# ======================
# Ollama Configuration
# ======================
OLLAMA_CONFIG = {
    "base_url": "http://localhost:11434/api",
    "model": "phi3:mini",  # Lightweight model optimized for CPU
    "options": {
        "num_ctx": 1024,           # Reduced context window for CPU
        "num_thread": max(1, os.cpu_count() - 1),  # Auto-thread detection
        "temperature": 0.3,        # More focused responses
        "stop": ["\n###", "\n##"]  # Better stopping criteria
    }
}


# ======================
# Flask Routes
# ======================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        logger.debug("Received analyze request")
        
        # Validate request contains JSON
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'error': 'Request must be JSON'}), 400
            
        # Parse and validate JSON structure
        audit_data = request.get_json()
        logger.debug(f"Received data keys: {list(audit_data.keys())}")
        
        # Check for required nested structure
        if not audit_data or 'audit_report' not in audit_data:
            logger.error("Missing 'audit_report' in data")
            return jsonify({'error': "Data must contain 'audit_report' object"}), 400
            
        audit_report = audit_data['audit_report']
        
        if not audit_report.get('exceptions'):
            logger.error("No exceptions found in audit_report")
            return jsonify({'error': "'audit_report' must contain 'exceptions' array"}), 400
            
        logger.info(f"Processing {len(audit_report['exceptions'])} exceptions for {audit_report.get('branch', 'unknown branch')}")
        
        # Prepare and validate prompt
        try:
            prompt = prepare_audit_prompt(audit_data)
            if len(prompt) > 10000:  # Safety check
                logger.warning("Very large prompt generated")
        except Exception as e:
            logger.error(f"Prompt preparation failed: {str(e)}")
            return jsonify({'error': f"Failed to prepare analysis prompt: {str(e)}"}), 400
            
        # Call Ollama with timeout
        try:
            analysis_result = query_ollama(prompt)
            if 'error' in analysis_result:
                logger.error(f"Ollama analysis failed: {analysis_result['error']}")
                return jsonify(analysis_result), 502  # Bad Gateway
        except requests.exceptions.Timeout:
            logger.error("Ollama request timed out")
            return jsonify({'error': 'Analysis timeout - try a smaller dataset'}), 504
            
        # Generate visualizations
        try:
            chart_urls = generate_charts(audit_report['exceptions'])
        except Exception as e:
            logger.error(f"Chart generation failed: {str(e)}")
            chart_urls = {}  # Continue without charts
            
        # Prepare metadata for response
        response_data = {
            'analysis': analysis_result,
            'charts': chart_urls,
            'metadata': {
                'branch': audit_report.get('branch'),
                'period': audit_report.get('period'),
                'exception_count': len(audit_report['exceptions'])
            }
        }
        
        logger.info("Analysis completed successfully")
        return jsonify(response_data)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received: {str(e)}")
        return jsonify({'error': 'Invalid JSON format'}), 400
    except Exception as e:
        logger.exception("Unexpected analysis error")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/generate-report', methods=['POST'])
def generate_report():
    try:
        data = request.json
        
        # Validate input
        if not data or 'analysis' not in data:
            return jsonify({'error': 'Invalid report data'}), 400
            
        doc = generate_word_document(data['analysis'])
        
        return send_file(
            doc,
            as_attachment=True,
            download_name='Audit_Report.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    except Exception as e:
        return jsonify({'error': f"Report generation failed: {str(e)}"}), 500

# ======================
# Core Functions
# ======================
def prepare_audit_prompt(audit_data):
    """Convert nested audit data into a structured prompt"""
    try:
        # Extract key components
        branch = audit_data['audit_report'].get('branch', 'Unknown branch')
        period = audit_data['audit_report'].get('period', 'Unknown period')
        exceptions = audit_data['audit_report'].get('exceptions', [])
        
        prompt = f"""You are an expert banking auditor analyzing exceptions from {branch} branch for {period}.
Provide:
1. Executive summary (1 paragraph)
2. Findings (list with: title, description, risk_level, impact)
3. Participants (extract from metadata if available)
4. Recommendations for each exception

Structure as JSON with these keys: summary, findings[], participants[], trends.

Audit Data:
{json.dumps(exceptions, indent=2)}"""
        
        return prompt
    except Exception as e:
        logger.error(f"Prompt preparation failed: {str(e)}")
        raise

def query_ollama(prompt: str) -> Dict[str, Any]:
    """Send prompt to Ollama with error handling"""
    try:
        payload = {
            "model": OLLAMA_CONFIG["model"],
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": OLLAMA_CONFIG["options"]
        }
        
        response = requests.post(
            f"{OLLAMA_CONFIG['base_url']}/generate",
            json=payload,
            timeout=120  # Extended timeout for CPU processing
        )
        response.raise_for_status()
        
        # Process streaming response
        full_response = ""
        for line in response.iter_lines():
            if line:
                decoded = json.loads(line.decode('utf-8'))
                full_response += decoded.get("response", "")
        
        return json.loads(full_response) if full_response else {"error": "Empty response from Ollama"}
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Ollama connection failed: {str(e)}"}
    except json.JSONDecodeError:
        return {"error": "Failed to parse Ollama response"}

def generate_charts(audit_data: Dict[str, Any]) -> Dict[str, str]:
    """Generate chart data for the frontend"""
    try:
        # Windows-safe temp directory
        temp_dir = os.path.join(os.environ.get('TEMP', ''), 'audit_charts')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Example: Severity distribution chart
        severities = count_severities(audit_data)
        plt.figure(figsize=(8, 4))
        plt.bar(severities.keys(), severities.values())
        plt.title('Exception Severity Distribution')
        severity_path = os.path.join(temp_dir, 'severity.png')
        plt.savefig(severity_path)
        plt.close()
        
        return {
            'severity': severity_path.replace('\\', '/'),
            # Add other charts as needed
        }
    except Exception as e:
        app.logger.error(f"Chart generation failed: {e}")
        return {}

def generate_word_document(analysis: Dict[str, Any]) -> BytesIO:
    """Create Word document from analysis"""
    doc = Document()
    
    # Title Page
    doc.add_heading('Banking Audit Exception Report', 0)
    doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Executive Summary
    doc.add_heading('Executive Summary', level=1)
    doc.add_paragraph(analysis.get('summary', 'No summary provided'))
    
    # Findings
    doc.add_heading('Detailed Findings', level=1)
    for finding in analysis.get('findings', []):
        doc.add_heading(finding.get('title', 'Untitled Finding'), level=2)
        doc.add_paragraph(finding.get('description', 'No description'))
        doc.add_paragraph(f"Severity: {finding.get('severity', 'unknown').upper()}")
        doc.add_paragraph(f"Recommendation: {finding.get('recommendation', 'None')}")
    
    # Participants
    if 'participants' in analysis:
        doc.add_heading('Participants Involved', level=1)
        table = doc.add_table(rows=1, cols=3)
        table.style = 'LightShading-Accent1'
        hdr = table.rows[0].cells
        hdr[0].text = 'Name'
        hdr[1].text = 'Role'
        hdr[2].text = 'Branch'
        
        for p in analysis['participants']:
            row = table.add_row().cells
            row[0].text = p.get('name', '')
            row[1].text = p.get('role', '')
            row[2].text = p.get('branch', '')
    
    # Save to memory
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ======================
# Helper Functions
# ======================
def count_severities(data: Dict[str, Any]) -> Dict[str, int]:
    """Count severity levels in audit data"""
    counts = {'low': 0, 'medium': 0, 'high': 0}
    for item in data.get('exceptions', []):
        sev = item.get('severity', '').lower()
        if sev in counts:
            counts[sev] += 1
    return counts

def validate_analysis_structure(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the analysis has required fields"""
    return {
        'summary': data.get('summary', 'No summary provided'),
        'findings': data.get('findings', []),
        'participants': data.get('participants', []),
        'trends': data.get('trends', 'No trends identified')
    }

# ======================
# Entry Point
# ======================
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5001,
        debug=True,
        threaded=True  # Better for handling multiple requests
    )