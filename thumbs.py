import os
import cv2
import numpy as np
import argparse
from pathlib import Path
import math

def create_thumbnail(source_path, dest_path, watermark=None):
    # Normalize paths to absolute paths for comparison
    source_path = os.path.abspath(source_path)
    dest_path = os.path.abspath(dest_path)
    
    # Check if source and destination paths are the same
    if source_path == dest_path:
        raise ValueError("Source and destination paths cannot be the same")
    
    # Check if source path exists
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source path does not exist: {source_path}")
    
    # Create destination path if it doesn't exist
    os.makedirs(dest_path, exist_ok=True)
    
    # Supported image extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    
    # Target total pixels (640 * 426 = 272,640)
    target_pixels = 640 * 426
    
    # Counter for processed files
    processed_count = 0
    
    # If no watermark image is provided, use text "mphoto"
    if watermark and os.path.exists(watermark):
        watermark_img = cv2.imread(watermark, cv2.IMREAD_UNCHANGED)
    else:
        watermark_img = None
    
    # Traverse source directory and its subdirectories
    for root, _, files in os.walk(source_path):
        for filename in files:
            if filename.lower().endswith(image_extensions):
                # Full path of source image
                src_file = os.path.join(root, filename)
                # Relative path
                rel_path = os.path.relpath(src_file, source_path)
                
                # Print currently processing image
                print(f"Processing: {rel_path}")
                
                # Read image
                img = cv2.imread(src_file)
                if img is None:
                    print(f"Warning: Unable to read image {rel_path}")
                    continue
                
                # Calculate scaling factor based on total pixels
                h, w = img.shape[:2]
                aspect_ratio = w / h
                # New area = target_pixels, w * h = target_pixels, w = aspect_ratio * h
                # Therefore: aspect_ratio * h * h = target_pixels
                new_h = int(math.sqrt(target_pixels / aspect_ratio))
                new_w = int(new_h * aspect_ratio)
                
                # Resize image
                resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                
                # Calculate watermark height (12% of thumbnail height)
                h, w = resized.shape[:2]
                wm_h = int(h * 0.12)  # Watermark height is 12% of image height
                
                # Create watermark
                if watermark_img is not None:
                    wm_w = int(watermark_img.shape[1] * wm_h / watermark_img.shape[0])
                    wm_resized = cv2.resize(watermark_img, (wm_w, wm_h))
                else:
                    # Use text watermark
                    text = "mphoto"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    # Adjust font scale based on watermark height
                    font_scale = wm_h / 40  # Adjust scale dynamically
                    text_size = cv2.getTextSize(text, font, font_scale, 2)[0]
                    wm_w = text_size[0]
                    wm_resized = np.zeros((wm_h, wm_w, 4), dtype=np.uint8)
                    cv2.putText(wm_resized, text, (0, wm_h-10), font, font_scale, (255, 255, 255, 128), 2)
                
                # Calculate watermark position (bottom-right corner)
                x = w - wm_w - 10  # 10 pixels margin
                y = h - wm_h - 10
                
                # Add watermark (handle transparency)
                if wm_resized.shape[-1] == 4:  # Has alpha channel
                    alpha = wm_resized[:, :, 3] / 255.0
                    for c in range(3):
                        resized[y:y+wm_h, x:x+wm_w, c] = (
                            (1 - alpha) * resized[y:y+wm_h, x:x+wm_w, c] + 
                            alpha * wm_resized[:, :, c]
                        )
                else:  # No alpha channel, direct blending
                    roi = resized[y:y+wm_h, x:x+wm_w]
                    blended = cv2.addWeighted(roi, 0.7, wm_resized[:, :, :3], 0.3, 0)
                    resized[y:y+wm_h, x:x+wm_w] = blended
                
                # Create destination file path
                dest_file = os.path.join(dest_path, rel_path)
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                
                # Save thumbnail
                cv2.imwrite(dest_file, resized)
                print(f"Saved: {rel_path} (Size: {new_w}x{new_h}, Pixels: {new_w * new_h})")
                processed_count += 1
    
    # Return the count of processed files
    return processed_count

def main():
    parser = argparse.ArgumentParser(description='Thumbnail creation tool')
    parser.add_argument('-s', '--source', required=True, help='Source image directory')
    parser.add_argument('-d', '--dest', required=True, help='Destination directory')
    parser.add_argument('-m', '--watermark', help='Watermark image path')
    
    args = parser.parse_args()
    
    try:
        processed_count = create_thumbnail(
            source_path=args.source,
            dest_path=args.dest,
            watermark=args.watermark
        )
        print("Processing completed!")
        print(f"Total files processed: {processed_count}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
