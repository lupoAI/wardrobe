from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
IMAGE_DIR = DATA_DIR / "images"
EMBEDDING_DIR = DATA_DIR / "embeddings"
DB_PATH = DATA_DIR / "wardrobe.sqlite3"

CATEGORIES = {
    "tops": ["shirt", "t-shirt", "tee", "blouse", "sweater", "hoodie", "tank", "polo"],
    "bottoms": ["trousers", "pants", "jeans", "shorts", "skirt", "leggings"],
    "outerwear": ["jacket", "coat", "blazer", "parka", "vest"],
    "shoes": ["shoes", "sneakers", "boots", "loafers", "sandals", "heels"],
    "accessories": ["belt", "hat", "cap", "scarf", "tie", "bag", "watch", "sunglasses"],
    "underwear": ["socks", "underwear", "bra"],
    "unknown": []
}
