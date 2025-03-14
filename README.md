# Massive / Marathon Photo Index and Search
**Searching for photos in a massive photo library can be a very time-consuming task.**This tool provides a convenient solution.  

The initial idea came from the **2025 Chilly Half**. I participated in the race as a **1:40 pacer**. The organizers generously shared all the official photos. However, finding my own pictures took far longer than my actual race time. This led me to an idea: **building a tool to automate photo retrieval**.

---

### **Technology Stack:**  
1. **DeepFace** for face detection and embedding.  
2. **PaddleOCR** for bib number recognition.  
3. **Python + Web Framework + JavaScript** for frontend development.  
4. **AWS deployment** with **S3 as the photo storage**.  

---

### **Project Plan:**  
1. [x] **Develop a backend photo scanning and indexing tool** to scan the photo library, detect faces and bib numbers, and store the data in a database.  
2. [x] **Develop a backend retrieval tool** that allows users to search for photos based on a provided face image or bib number and package the results.  
3. [ ] **Complete frontend development and testing.**  
4. [ ] **Develop and test deployment scripts.**  
5. [ ]**Deploy the system on AWS.**  


