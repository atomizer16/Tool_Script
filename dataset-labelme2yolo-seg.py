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
    base_name = json_path.stem
    parent_dir = json_path.parent
    
    try:
        image_copied = False
        for file_path in parent_dir.iterdir():
            if file_path.is_file():
                if file_path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
                    if file_path.stem.lower() == base_name.lower():
                        target_dir = target_folder / "images" / task
                        target_dir.mkdir(parents=True, exist_ok=True)
                        target_path = target_dir / file_path.name
                        shutil.copy2(file_path, target_path)
                        image_copied = True
                        break
        
        if not image_copied:
            print(f"Warning: No image found for {json_path}")
            available_images = [f.name for f in parent_dir.iterdir() 
                               if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTS]
            if available_images:
                print(f"  Available images in directory: {available_images[:5]}")
                
    except Exception as e:
        print(f"Error copying image for {json_path}: {e}")


def json_to_yolo_seg(json_path: Path, sorted_keys: list):
    """
    Convert LabelMe JSON annotation to YOLO format for segmentation (pixel-level annotations).
    
    Args:
        json_path: Path to LabelMe JSON file
        sorted_keys: Sorted list of class names
    
    Returns:
        List of YOLO format annotation strings (segmentation masks)
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
        if len(points) < 3:
            print(f"Warning: Invalid points in {json_path} for label {label}")
            continue
        
        class_idx = sorted_keys.index(label)
        
        # Convert points to mask (polygon)
        mask = [(x / width, y / height) for x, y in points]
        
        # Save mask in YOLO format for segmentation (each mask as class index + points)
        mask_string = f"{class_idx} " + " ".join([f"{x:.6f} {y:.6f}" for x, y in mask]) + "\n"
        yolo_lines.append(mask_string)
    
    return yolo_lines


def create_directory_if_not_exists(directory_path):
    """Create directory if it doesn't exist."""
    directory_path.mkdir(parents=True, exist_ok=True)


def create_yaml(output_folder: Path, sorted_keys: list):
    """
    Create YAML configuration file for YOLO training (for segmentation).
    
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
    
    names_dict = {idx: name for idx, name in enumerate(sorted_keys)}
    
    yaml_dict = {
        "path": output_folder.absolute().as_posix(),
        "train": train_img_path.as_posix(),
        "val": val_img_path.as_posix(),
        "nc": len(sorted_keys),
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
    
    sorted_keys = sorted(label_counts.keys(), key=lambda k: label_counts[k], reverse=True)
    
    print(f"Found {len(sorted_keys)} classes: {sorted_keys}")
    print(f"Found {len(json_file_paths)} JSON files")
    
    return sorted_keys, json_file_paths


def labelme_to_yolo_seg(
    json_file_paths: list, output_folder: Path, sorted_keys: list, split_rate: float
):
    """
    Convert LabelMe dataset to YOLO format for segmentation and split into train/val sets.
    
    Args:
        json_file_paths: List of JSON file paths
        output_folder: Output dataset root directory
        sorted_keys: Sorted list of class names
        split_rate: Ratio for training set (e.g., 0.8 for 80% train, 20% val)
    """
    random.shuffle(json_file_paths)
    
    split_point = int(split_rate * len(json_file_paths))
    train_set = json_file_paths[:split_point]
    val_set = json_file_paths[split_point:]
    
    print(f"Training samples: {len(train_set)}")
    print(f"Validation samples: {len(val_set)}")
    
    # Process training set
    print("\nProcessing training set...")
    for json_file_path in tqdm(train_set, desc="Training"):
        try:
            yolo_lines = json_to_yolo_seg(json_file_path, sorted_keys)
            
            if yolo_lines:
                txt_name = json_file_path.stem + ".txt"
                output_label_path = output_folder / "labels" / "train" / txt_name
                output_label_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_label_path, "w") as f:
                    f.writelines(yolo_lines)
                
                copy_labeled_img(json_file_path, output_folder, task="train")
            else:
                print(f"Warning: No valid annotations in {json_file_path}")
        except Exception as e:
            print(f"Error processing {json_file_path}: {e}")
    
    # Process validation set
    print("\nProcessing validation set...")
    for json_file_path in tqdm(val_set, desc="Validation"):
        try:
            yolo_lines = json_to_yolo_seg(json_file_path, sorted_keys)
            
            if yolo_lines:
                txt_name = json_file_path.stem + ".txt"
                output_label_path = output_folder / "labels" / "val" / txt_name
                output_label_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_label_path, "w") as f:
                    f.writelines(yolo_lines)
                
                copy_labeled_img(json_file_path, output_folder, task="val")
            else:
                print(f"Warning: No valid annotations in {json_file_path}")
        except Exception as e:
            print(f"Error processing {json_file_path}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert LabelMe dataset to YOLO format for segmentation")
    parser.add_argument("input_folder", help="Input folder containing LabelMe JSON files")
    parser.add_argument("output_folder", help="Output folder for YOLO formatted dataset")
    parser.add_argument("split_rate", type=float, help="Train/validation split ratio (e.g., 0.8 for 80% train)")
    
    args = parser.parse_args()
    
    input_folder = Path(args.input_folder)
    output_folder = Path(args.output_folder)
    split_rate = args.split_rate
    
    if not 0 < split_rate < 1:
        raise ValueError(f"Split rate must be between 0 and 1, got {split_rate}")
    
    create_directory_if_not_exists(output_folder)
    
    sorted_keys, json_file_paths = get_labels_and_json_path(input_folder)
    
    create_yaml(output_folder, sorted_keys)
    
    labelme_to_yolo_seg(json_file_paths, output_folder, sorted_keys, split_rate)
    
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