"""
list_cameras.py — Détecte toutes les caméras disponibles sur le système.

Usage:
    source .venv/bin/activate
    python list_cameras.py

Affiche l'index à utiliser dans CAMERA_SOURCE du fichier .env.
L'iPhone via Continuity Camera apparaît généralement à l'index 1 ou 2.
"""

import os
import cv2

# Supprime les logs OBSENSOR / depth-sensor de OpenCV
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"


def list_cameras(max_test: int = 6) -> list:
    found = []
    print("Recherche des caméras disponibles (backend AVFoundation)...\n")

    for i in range(max_test):
        # AVFoundation = backend natif macOS — évite le bruit OBSENSOR
        cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
        if cap.isOpened():
            width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps    = cap.get(cv2.CAP_PROP_FPS)
            ret, _ = cap.read()
            cap.release()
            found.append({
                "index": i,
                "resolution": f"{width}x{height}",
                "fps": round(fps, 1),
                "readable": ret,
            })
            status = "✅ OK" if ret else "⚠️  ouvert mais pas de frame"
            label  = "iPhone (Continuity Camera)" if i > 0 else "MacBook FaceTime HD"
            print(f"  [{i}] {label:28s}  {width}x{height} @ {fps:.0f}fps  {status}")
        else:
            cap.release()

    print()
    if not found:
        print("Aucune caméra trouvée.")
        print("→ Vérifiez les permissions dans Système → Confidentialité → Caméra")
    else:
        readable = [c for c in found if c["readable"]]
        if readable:
            print(f"Caméras utilisables : {[c['index'] for c in readable]}")
            print(f"\nPour utiliser l'index {readable[0]['index']} :")
            print(f"  Mettez dans backend/.env :  CAMERA_SOURCE={readable[0]['index']}")
            if len(readable) > 1:
                print(f"\nSi l'index {readable[1]['index']} est votre iPhone (Continuity Camera) :")
                print(f"  Mettez dans backend/.env :  CAMERA_SOURCE={readable[1]['index']}")

    return found


if __name__ == "__main__":
    list_cameras()
