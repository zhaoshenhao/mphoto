# INSTALL
# It's pretty tricky:
- Photo scaning requires GPU. We need to resolve the cuda conflict between torch, tensorflow.
- We disable the GPU in photo extracting. We can ignore the conflict.

# For photo scaning process:
```bash
pip install -r requirements.txt
pip install 'tensorflow[and-cuda]'
```

# For web application:
```bash
pip install -r requirements.txt
pip install -r web/backend/requirements.txt
```

