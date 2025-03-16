# **Running Instructions**

## **Frontend**
- Place the `frontend/` folder on a static server (e.g., **Nginx**) or open `index.html` directly in a browser (**CORS configuration or local backend support required**).
- **Cropper.js** is loaded via CDN, so ensure network connectivity.

## **Backend**
### **1. Install dependencies**
```bash
pip install -r requirements.txt
```

### **2. Update Configuration**
- Modify config.yaml to set up S3 and DynamoDB configurations.

### **3. Run the Backend**
```
uvicorn main:app --reload
```

### **4. Others
- S3 and DynamoDB must be configured with the appropriate permissions beforehand.
- mphoto.extract returns an array of images; adjustments may be needed based on the actual implementation.

