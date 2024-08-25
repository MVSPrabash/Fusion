from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import secrets
import os
import google.generativeai as genai

app = Flask(__name__)
app.secret_key = secrets.token_hex(24)

# Gemini Config
# Configure the API key for Google Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Create the model configuration
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
)


# users.db :
#       - users : usernames and hashed passwords
#       - financial_assets: assets
# Intialize the database
def init_sqlite_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()          # Cursor that moves across database

    # Username and passwords table: users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Financial Assets table with asset_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS financial_assets (
            asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            asset_name TEXT NOT NULL,
            asset_income REAL NOT NULL,
            asset_expenditure REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()


# Route / : home page
@app.route('/', methods=['GET'])
def home():
    if 'username' in session:
        flash(f'Logged in as {session.get('username')}', 'success')
        return redirect('/dashboard', code=302) # code 302 : found
    return render_template('index.html')

# Route /about : about page
@app.route('/about', methods=['GET'])
def about():
    return render_template('about.html')

### LOGIN MANAGER ###
# Route /login : login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['username'] = username                  
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials, please try again.', 'danger')

    return render_template('login.html')

# Route /register : register page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirmPassword = request.form['confirmPassword']
        if password != confirmPassword:
            flash("Passwords don't match", 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        conn.close()

        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Route /logout
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

### DASHBOARD ###
# Route /dashboard : dashboard page
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' in session:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Fetch the user's assets
        cursor.execute('''
            SELECT asset_id, asset_name, asset_income, asset_expenditure
            FROM financial_assets
            JOIN users ON financial_assets.user_id = users.id
            WHERE users.username = ?
        ''', (session['username'],))
        assets = cursor.fetchall()
        
        conn.close()

        response_text = None
        if request.method == "POST":
            user_prompt = request.form.get("prompt")
            include_asset = request.form.get("include_asset")
            if user_prompt != '':
                if include_asset:
                    asset_details = '\n'.join(
                        f"Asset Name: {asset[1]}, Income: {asset[2]}, Expenditure: {asset[3]}"
                        for asset in assets
                    )
                    prompt = (
                        "Only generative content related to Assistance in Financial, economy and money. "
                        "Deny the question if it's off topic from Financial. Use rupees "
                        "Only If I ask now: Asset Details:" + asset_details + ' Prompt :' + user_prompt +
                        "Don't warn the user about AI Generated Content. Output in HTML body format"
                    )
                else:
                    prompt = (
                        "Only generative content related to Assistance in Financial, economy and money. "
                        "Deny the question if it's off topic from Financial. Use rupees  "
                        "Only If I ask now: " + user_prompt +
                        "Don't warn the user about AI Generated Content. Output in HTML body format"
                    )
                chat_session = model.start_chat(history=[])
                response = chat_session.send_message(prompt)
                response_text = response.text

        # Pass response_text to the template
        return render_template('dashboard.html', assets=assets, response=response_text)
    else:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

### ASSET MANAGER ###
# Route /dashboard/add_asset : add assets
@app.route('/dashboard/add_asset', methods=['GET', 'POST'])
def add_asset():
    if 'username' in session:
        if request.method == 'POST':
            asset_name = request.form['asset_name']
            asset_income = request.form['asset_income']
            asset_expenditure = request.form['asset_expenditure']

            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE username = ?', (session['username'],))
            user_id = cursor.fetchone()[0]

            cursor.execute('''
                INSERT INTO financial_assets (user_id, asset_name, asset_income, asset_expenditure)
                VALUES (?, ?, ?, ?)
            ''', (user_id, asset_name, asset_income, asset_expenditure))
            conn.commit()
            conn.close()

            flash('Asset added successfully!', 'success')
            return redirect(url_for('dashboard'))

        return render_template('add_asset.html')
    else:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

# Route /dashboard/remove_asset : remove an asset
@app.route('/dashboard/remove_asset/<int:asset_id>', methods=['POST'])
def remove_asset(asset_id):
    if 'username' in session:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM financial_assets
            WHERE asset_id = ? AND user_id = (SELECT id FROM users WHERE username = ?)
        ''', (asset_id, session['username']))

        conn.commit()
        conn.close()

        flash('Asset removed successfully!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))


@app.route('/dashboard/modify_asset/<int:asset_id>', methods=['GET', 'POST'])
def modify_asset(asset_id):
    if 'username' in session:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        if request.method == 'POST':
            asset_name = request.form.get('asset_name')  # Ensure this is provided
            asset_income = request.form.get('asset_income')
            asset_expenditure = request.form.get('asset_expenditure')

            cursor.execute('''
                UPDATE financial_assets
                SET asset_name = ?, asset_income = ?, asset_expenditure = ?
                WHERE asset_id = ? AND user_id = (SELECT id FROM users WHERE username = ?)
            ''', (asset_name, asset_income, asset_expenditure, asset_id, session['username']))

            conn.commit()
            conn.close()

            flash('Asset updated successfully!', 'success')
            return redirect(url_for('dashboard'))

        cursor.execute('''
            SELECT asset_id, asset_name, asset_income, asset_expenditure
            FROM financial_assets
            WHERE asset_id = ? AND user_id = (SELECT id FROM users WHERE username = ?)
        ''', (asset_id, session['username']))
        asset = cursor.fetchone()
        conn.close()

        if asset:
            return render_template('modify_asset.html', asset=asset, asset_id=asset_id)
        else:
            flash('Asset not found or access denied.', 'danger')
            return redirect(url_for('dashboard'))
    else:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))


### TIPS MANAGER ###
# route: /tips - tips sections


if __name__ == '__main__':
    init_sqlite_db()            # Intialize the users database
    app.run(port=5000 ,debug=True)
