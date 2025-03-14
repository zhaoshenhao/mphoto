# Resolve cuda conflict between torch and tensorflow
1. torch has backward compatible.
2. Install with requirements.txt first
3. Then manually install tensorflow and ignore the conflict
```bash
pip install -r requirements.txt
pip install torch=2.6.0 torchvision==0.21.0
pip install 'tensorflow[and-cuda]'
