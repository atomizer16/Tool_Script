# JSON转目标检测TXT格式
import json
import random
import yaml
import argparse
import shutil
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm

# Set random seed for reproducibility
random.seed(114514)

# Supported image extensions (case-insensitive matching)
SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', 
                         '.tif', '.tiff', '.dng', '.mpo', '.pfm'}


def copy_labeled_img(json_path: Path, target_folder: Path, task: str):
    """
    Copy the corresponding image file for a given JSON annotation file.
    Supports case-insensitive filename matching.
    
    Args:
        json_path: Path to the JSON file
        target_folder: Output folder (dataset root)
        task: Either 'train' or 'val'
    """
    # Get the base name without extension
    base_name = json_path.stem
    parent_dir = json_path.parent
    
    # Find all files in the same directory
    try:
        # Look for an image file with matching base name (case-insensitive)
        image_copied = False
        for file_path in parent_dir.iterdir():
            if file_path.is_file():
                # Check if file extension is a supported image format
                if file_path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
                    # Check if filename matches (case-insensitive)
                    if file_path.stem.lower() == base_name.lower():
                        # Copy the image
                        target_dir = target_folder / "images" / task
                        target_dir.mkdir(parents=True, exist_ok=True)
                        target_path = target_dir / file_path.name
                        shutil.copy2(file_path, target_path)
                        image_copied = True
                        break
        
        if not image_copied:
            print(f"Warning: No image found for {json_path}")
            # Optional: List available image files for debugging
            available_images = [f.name for f in parent_dir.iterdir() 
                               if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTS]
            if available_images:
                print(f"  Available images in directory: {available_images[:5]}")
                
    except Exception as e:
        print(f"Error copying image for {json_path}: {e}")


def json_to_yolo(json_path: Path, sorted_keys: list):
    """
    Convert LabelMe JSON annotation to YOLO format.
    
    Args:
        json_path: Path to LabelMe JSON file
        sorted_keys: Sorted list of class names
    
    Returns:
        List of YOLO format annotation strings
    """
    with open(json_path, "r") as f:
        labelme_data = json.load(f)
    
    # Get image dimensions
    width = labelme_data.get("imageWidth", 0)
    height = labelme_data.get("imageHeight", 0)
    
    if width == 0 or height == 0:
        print(f"Warning: Invalid image dimensions in {json_path}")
        return []
    
    yolo_lines = []
    
    for shape in labelme_data.get("shapes", []):
        label = shape.get("label", "")
        if label not in sorted_keys:
            print(f"Warning: Label '{label}' not found in class list")
            continue
        
        points = shape.get("points", [])
        if len(points) < 2:
            print(f"Warning: Invalid points in {json_path} for label {label}")
            continue
        
        class_idx = sorted_keys.index(label)
        
        # Get the two points (top-left and bottom-right or any order)
        x1, y1 = points[0]
        x2, y2 = points[1]
        
        # Calculate bounding box coordinates
        x_min = min(x1, x2)
        x_max = max(x1, x2)
        y_min = min(y1, y2)
        y_max = max(y1, y2)
        
        # Calculate YOLO format (normalized center x, center y, width, height)
        box_width = (x_max - x_min) / width
        box_height = (y_max - y_min) / height
        x_center = ((x_min + x_max) / 2) / width
        y_center = ((y_min + y_max) / 2) / height
        
        # Clamp values to [0, 1] range
        x_center = max(0.0, min(x_center, 1.0))
        y_center = max(0.0, min(y_center, 1.0))
        box_width = max(0.0, min(box_width, 1.0))
        box_height = max(0.0, min(box_height, 1.0))
        
        # Format with 6 decimal places for precision
        txt_string = f"{class_idx} {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}\n"
        yolo_lines.append(txt_string)
    
    return yolo_lines


def create_directory_if_not_exists(directory_path):
    """Create directory if it doesn't exist."""
    directory_path.mkdir(parents=True, exist_ok=True)


def create_yaml(output_folder: Path, sorted_keys: list):
    """
    Create YAML configuration file for YOLO training.
    
    Args:
        output_folder: Root directory of the dataset
        sorted_keys: Sorted list of class names
    """
    train_img_path = Path("images") / "train"
    val_img_path = Path("images") / "val"
    train_label_path = Path("labels") / "train"
    val_label_path = Path("labels") / "val"
    
    # Create required directories
    for path in [train_img_path, val_img_path, train_label_path, val_label_path]:
        create_directory_if_not_exists(output_folder / path)
    
    # Create class names dictionary
    names_dict = {idx: name for idx, name in enumerate(sorted_keys)}
    
    # Create YAML structure
    yaml_dict = {
        "path": output_folder.absolute().as_posix(),  # Use absolute path
        "train": train_img_path.as_posix(),
        "val": val_img_path.as_posix(),
        "nc": len(sorted_keys),  # Number of classes
        "names": names_dict,
    }
    
    yaml_file_path = output_folder / "yolo.yaml"
    with open(yaml_file_path, "w") as yaml_file:
        yaml.dump(yaml_dict, yaml_file, default_flow_style=False, sort_keys=False)
    
    print(f"YAML configuration created at: {yaml_file_path.absolute().as_posix()}")
    print(f"Classes: {sorted_keys}")


def get_labels_and_json_path(input_folder: Path):
    """
    Extract all unique labels from JSON files and get list of JSON file paths.
    
    Args:
        input_folder: Root folder containing LabelMe JSON files
    
    Returns:
        tuple: (sorted list of unique labels, list of JSON file paths)
    """
    json_file_paths = list(input_folder.rglob("*.json"))
    
    if not json_file_paths:
        raise ValueError(f"No JSON files found in {input_folder}")
    
    label_counts = defaultdict(int)
    
    for json_file_path in json_file_paths:
        try:
            with open(json_file_path, "r") as f:
                labelme_data = json.load(f)
            
            for shape in labelme_data.get("shapes", []):
                label = shape.get("label", "")
                if label:
                    label_counts[label] += 1
        except Exception as e:
            print(f"Warning: Could not read {json_file_path}: {e}")
            continue
    
    if not label_counts:
        raise ValueError(f"No valid labels found in JSON files in {input_folder}")
    
    # Sort labels by their occurrence count in descending order
    sorted_keys = sorted(label_counts.keys(), key=lambda k: label_counts[k], reverse=True)
    
    print(f"Found {len(sorted_keys)} classes: {sorted_keys}")
    print(f"Found {len(json_file_paths)} JSON files")
    
    return sorted_keys, json_file_paths


def labelme_to_yolo(
    json_file_paths: list, output_folder: Path, sorted_keys: list, split_rate: float
):
    """
    Convert LabelMe dataset to YOLO format and split into train/val sets.
    
    Args:
        json_file_paths: List of JSON file paths
        output_folder: Output dataset root directory
        sorted_keys: Sorted list of class names
        split_rate: Ratio for training set (e.g., 0.8 for 80% train, 20% val)
    """
    # Randomly shuffle the list of JSON file paths
    random.shuffle(json_file_paths)
    
    # Calculate the split point between training and validation sets
    split_point = int(split_rate * len(json_file_paths))
    train_set = json_file_paths[:split_point]
    val_set = json_file_paths[split_point:]
    
    print(f"Training samples: {len(train_set)}")
    print(f"Validation samples: {len(val_set)}")
    
    # Process training set
    print("\nProcessing training set...")
    for json_file_path in tqdm(train_set, desc="Training"):
        try:
            # Convert JSON to YOLO format
            yolo_lines = json_to_yolo(json_file_path, sorted_keys)
            
            if yolo_lines:
                # Save YOLO annotation file
                txt_name = json_file_path.stem + ".txt"
                output_label_path = output_folder / "labels" / "train" / txt_name
                output_label_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_label_path, "w") as f:
                    f.writelines(yolo_lines)
                
                # Copy corresponding image
                copy_labeled_img(json_file_path, output_folder, task="train")
            else:
                print(f"Warning: No valid annotations in {json_file_path}")
        except Exception as e:
            print(f"Error processing {json_file_path}: {e}")
    
    # Process validation set
    print("\nProcessing validation set...")
    for json_file_path in tqdm(val_set, desc="Validation"):
        try:
            # Convert JSON to YOLO format
            yolo_lines = json_to_yolo(json_file_path, sorted_keys)
            
            if yolo_lines:
                # Save YOLO annotation file
                txt_name = json_file_path.stem + ".txt"
                output_label_path = output_folder / "labels" / "val" / txt_name
                output_label_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_label_path, "w") as f:
                    f.writelines(yolo_lines)
                
                # Copy corresponding image
                copy_labeled_img(json_file_path, output_folder, task="val")
            else:
                print(f"Warning: No valid annotations in {json_file_path}")
        except Exception as e:
            print(f"Error processing {json_file_path}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert LabelMe dataset to YOLO format")
    parser.add_argument("input_folder", help="Input folder containing LabelMe JSON files")
    parser.add_argument("output_folder", help="Output folder for YOLO formatted dataset")
    parser.add_argument("split_rate", type=float, help="Train/validation split ratio (e.g., 0.8 for 80% train)")
    
    args = parser.parse_args()
    
    input_folder = Path(args.input_folder)
    output_folder = Path(args.output_folder)
    split_rate = args.split_rate
    
    # Validate split rate
    if not 0 < split_rate < 1:
        raise ValueError(f"Split rate must be between 0 and 1, got {split_rate}")
    
    # Create output directory
    create_directory_if_not_exists(output_folder)
    
    # Get all labels and JSON files
    print("Scanning input folder...")
    sorted_keys, json_file_paths = get_labels_and_json_path(input_folder)
    
    # Create YAML configuration
    print("\nCreating YAML configuration...")
    create_yaml(output_folder, sorted_keys)
    
    # Convert dataset
    print("\nConverting dataset...")
    labelme_to_yolo(json_file_paths, output_folder, sorted_keys, split_rate)
    
    print("\n✅ Conversion completed successfully!")
    print(f"Dataset saved to: {output_folder.absolute()}")
    print("\nDataset structure:")
    print(f"  {output_folder}/")
    print(f"    ├── images/")
    print(f"    │   ├── train/  ({len([p for p in (output_folder/'images'/'train').glob('*') if p.is_file()])} images)")
    print(f"    │   └── val/    ({len([p for p in (output_folder/'images'/'val').glob('*') if p.is_file()])} images)")
    print(f"    ├── labels/")
    print(f"    │   ├── train/  ({len([p for p in (output_folder/'labels'/'train').glob('*.txt') if p.is_file()])} labels)")
    print(f"    │   └── val/    ({len([p for p in (output_folder/'labels'/'val').glob('*.txt') if p.is_file()])} labels)")
    print(f"    └── yolo.yaml")
