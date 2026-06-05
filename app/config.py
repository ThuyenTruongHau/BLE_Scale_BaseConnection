import os
from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "15"))
NAME_HINTS = _split_csv(
    os.getenv(
        "NAME_HINTS",
        "Scale,SCALE,BLE,Weight,WEIGHT,JIN,Jinlyun,LYUN,JS",
    )
)
SERVICE_HINTS = _split_csv(
    os.getenv(
        "SERVICE_HINTS",
        "181d,fff0,ffe0,2a9d",
    )
)
CORS_ORIGINS = _split_csv(
    os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
)
# uni_js_only = chỉ parseHexToType UNI; auto = thử thêm ffe_qn, chipsea, generic
WEIGHT_PARSER = os.getenv("WEIGHT_PARSER", "uni_js_only").strip().lower()
