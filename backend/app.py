from flask import Flask, jsonify
from flask_cors import CORS
import config

# Initialize flask app
app = Flask(__name__)
app.config.from_object(config.Config)

# Enable CORS for the React frontend port (Vite running on localhost:5173)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Slopee Backend is running!"})

if __name__ == '__main__':
    # Run the server in debug mode at port 5000
    app.run(debug=True, port=5000)
