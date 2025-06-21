from flask import Flask, request, send_file, render_template_string
import pandas as pd
import hashlib
import os
import tempfile

app = Flask(__name__)

HTML_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
  <title>Email Suppression Tool</title>
  <style>
    body { font-family: Arial; background-color: #f9f9f9; padding: 40px; }
    h2, h3 { color: #333; }
    form { background: #fff; padding: 20px; border-radius: 8px; width: 400px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    input[type="file"], input[type="submit"] {
      margin-top: 10px; padding: 8px; width: 100%; border-radius: 5px; border: 1px solid #ccc;
    }
    .error { color: red; margin-top: 20px; }
    table { border-collapse: collapse; margin-top: 20px; }
    th, td { border: 1px solid #ccc; padding: 5px; }
  </style>
</head>
<body>
  <h2>Email Suppression Upload</h2>
  <form method="post" enctype="multipart/form-data">
    <label>Email file (.txt or .csv):</label><br>
    <input type="file" name="emails" required><br><br>
    <label>Suppression file (.txt or .csv):</label><br>
    <input type="file" name="suppression" required><br><br>
    <input type="submit" value="Submit">
  </form>
  {% if error %}<div class="error"><strong>Error:</strong> {{ error }}</div>{% endif %}
  {% if clean_sample %}
    <h3>Results</h3>
    <p>Clean emails: {{ clean_count }}</p>
    <p>Suppressed emails: {{ suppressed_count }}</p>
    <a href="/download/clean">Download Clean Emails</a><br>
    <a href="/download/suppressed">Download Suppressed Emails</a><br><br>
    <h4>Sample Clean Emails</h4>
    <table>
      <tr><th>Email</th></tr>
      {% for email in clean_sample %}
        <tr><td>{{ email }}</td></tr>
      {% endfor %}
    </table>
  {% endif %}
</body>
</html>
'''

def md5_hash(email):
    return hashlib.md5(email.strip().lower().encode()).hexdigest()

def load_suppression_list(suppression_file):
    ext = os.path.splitext(suppression_file.filename)[1].lower()
    suppression_emails = []
    try:
        if ext == '.csv':
            df = pd.read_csv(suppression_file)
            if 'email' not in df.columns:
                return None, "Suppression CSV must have 'email' column."
            suppression_emails = df['email'].dropna().astype(str).tolist()
        else:
            suppression_emails = [line.decode('utf-8').strip() for line in suppression_file if line.strip()]
    except Exception as e:
        return None, f"Failed to process suppression file: {str(e)}"

    suppression_hashes = set()
    for entry in suppression_emails:
        if len(entry) == 32 and all(c in '0123456789abcdef' for c in entry.lower()):
            suppression_hashes.add(entry.lower())
        else:
            suppression_hashes.add(md5_hash(entry))
    return suppression_hashes, None

@app.route('/supp', methods=['GET', 'POST'])
def supp_tool():
    error = None
    clean_sample = []
    clean_count = suppressed_count = 0

    if request.method == 'POST':
        emails_file = request.files.get('emails')
        suppression_file = request.files.get('suppression')

        if not emails_file or not suppression_file:
            error = "Both files are required."
        else:
            suppression_hashes, error = load_suppression_list(suppression_file)

            if not error:
                ext = os.path.splitext(emails_file.filename)[1].lower()
                try:
                    if ext == '.csv':
                        df = pd.read_csv(emails_file)
                        if 'email' not in df.columns:
                            error = "Emails CSV must have 'email' column."
                        else:
                            emails = df['email'].dropna().astype(str).tolist()
                    else:
                        emails = [line.decode('utf-8').strip() for line in emails_file if line.strip()]
                except Exception as e:
                    error = f"Failed to process email file: {str(e)}"

                if not error:
                    df = pd.DataFrame(emails, columns=['email'])
                    df['md5'] = df['email'].apply(md5_hash)

                    clean_df = df[~df['md5'].isin(suppression_hashes)]
                    suppressed_df = df[df['md5'].isin(suppression_hashes)]

                    clean_sample = clean_df['email'].head(5).tolist()
                    clean_count = len(clean_df)
                    suppressed_count = len(suppressed_df)

                    tmp_dir = tempfile.gettempdir()
                    clean_df[['email']].to_csv(os.path.join(tmp_dir, "clean_emails.txt"), index=False, header=False)
                    suppressed_df[['email']].to_csv(os.path.join(tmp_dir, "suppressed_emails.txt"), index=False, header=False)

    return render_template_string(HTML_TEMPLATE, error=error, clean_sample=clean_sample,
                                  clean_count=clean_count, suppressed_count=suppressed_count)

@app.route('/download/<file_type>')
def download(file_type):
    tmp_dir = tempfile.gettempdir()
    file_map = {
        'clean': os.path.join(tmp_dir, "clean_emails.txt"),
        'suppressed': os.path.join(tmp_dir, "suppressed_emails.txt")
    }
    path = file_map.get(file_type)
    if path and os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
