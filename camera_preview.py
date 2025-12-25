#!/usr/bin/env python3
"""
Simple camera preview GUI for checking camera placement
Shows live camera feed with ROI region highlighted
Accounts for card detection warping (may rotate/transform the card)
"""

import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
import threading
import sys
import os
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from card_sorter.config_loader import AppConfig


def detect_card_and_warp(frame):
    """Detect card in frame and return warped version (same as in mtg_sorter_cli)"""
    if frame is None:
        return None
    
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        cnt = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4:
            return None
        pts = approx.reshape(4, 2).astype("float32")
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)
        tl = pts[np.argmin(s)]
        br = pts[np.argmax(s)]
        tr = pts[np.argmin(diff)]
        bl = pts[np.argmax(diff)]
        ordered = np.array([tl, tr, br, bl], dtype="float32")
        w = 720
        h = 1024
        dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype="float32")
        M = cv2.getPerspectiveTransform(ordered, dst)
        warped = cv2.warpPerspective(frame, M, (w, h))
        return warped
    except Exception as e:
        return None


class CameraPreview:
    def __init__(self, root, camera_idx=0, resolution=(640, 480)):
        self.root = root
        self.root.title("Camera Preview - Card Detection")
        self.root.geometry("900x900")
        
        self.camera_idx = camera_idx
        self.resolution = resolution
        self.cap = None
        self.running = False
        self.frame_count = 0
        self.card_detected = False
        
        # Load default ROI from config
        try:
            cfg = AppConfig()
            self.roi = cfg.name_roi  # (x1, y1, x2, y2)
        except:
            self.roi = (0.08, 0.08, 0.92, 0.22)  # Default fallback
        
        # Create GUI
        self._build_layout()
        
        # Start camera thread
        self.start_preview()
    
    def _build_layout(self):
        """Build the GUI layout"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Camera Feed with Detected Card (Warped View)", font=("Arial", 12, "bold")).pack(fill=tk.X)
        
        # Camera preview label
        self.preview_label = tk.Label(main_frame, bg="black", width=640, height=480)
        self.preview_label.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Starting camera...")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="blue")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(status_frame, text="Card:").pack(side=tk.LEFT, padx=20)
        self.card_var = tk.StringVar(value="Not detected")
        self.card_label = ttk.Label(status_frame, textvariable=self.card_var, foreground="red")
        self.card_label.pack(side=tk.LEFT, padx=5)
        
        # Frame counter
        ttk.Label(status_frame, text="Frames:").pack(side=tk.LEFT, padx=20)
        self.frame_var = tk.StringVar(value="0")
        ttk.Label(status_frame, textvariable=self.frame_var).pack(side=tk.LEFT, padx=5)
        
        # ROI info
        info_frame = ttk.LabelFrame(main_frame, text="Current ROI Settings", padding=5)
        info_frame.pack(fill=tk.X, pady=5)
        
        roi_text = f"ROI: x={self.roi[0]:.0%}-{self.roi[2]:.0%}, y={self.roi[1]:.0%}-{self.roi[3]:.0%}"
        ttk.Label(info_frame, text=roi_text, font=("Courier", 10)).pack(side=tk.LEFT)
        
        ttk.Label(info_frame, text="(Red rectangle shows OCR region)", foreground="red").pack(side=tk.LEFT, padx=10)
        
        # Instructions
        help_frame = ttk.LabelFrame(main_frame, text="How to Use", padding=5)
        help_frame.pack(fill=tk.X, pady=5)
        
        help_text = (
            "This preview shows the WARPED detected card (rotated to vertical).\n"
            "The RED RECTANGLE shows what region is being sent to OCR for text recognition.\n"
            "If the rectangle is capturing the wrong area, adjust ROI in the OCR test:\n"
            "  python mtg_sorter_cli.py test-ocr-live --roi 0.08 0.04 0.92 0.14"
        )
        ttk.Label(help_frame, text=help_text, justify=tk.LEFT).pack(fill=tk.X)
        
        # Controls
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Close", command=self.stop_preview).pack(side=tk.LEFT)
    
    def start_preview(self):
        """Start the camera preview thread"""
        self.running = True
        self.thread = threading.Thread(target=self._preview_loop, daemon=True)
        self.thread.start()
    
    def stop_preview(self):
        """Stop the camera preview"""
        self.running = False
        if self.cap:
            self.cap.release()
        self.root.quit()
    
    def _preview_loop(self):
        """Main preview loop running in background thread"""
        try:
            # Open camera
            self.cap = cv2.VideoCapture(self.camera_idx)
            if not self.cap or not self.cap.isOpened():
                self.root.after(0, lambda: self.status_var.set("ERROR: Camera not found"))
                return
            
            # Set resolution
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            
            self.root.after(0, lambda: self.status_var.set("Camera ready"))
            
            while self.running:
                ret, frame = self.cap.read()
                if not ret:
                    self.root.after(0, lambda: self.status_var.set("ERROR: Failed to read frame"))
                    break
                
                self.frame_count += 1
                
                # Detect and warp card
                warped = detect_card_and_warp(frame)
                
                if warped is not None:
                    # Use warped card image
                    self.card_detected = True
                    display_frame = warped
                    h, w = warped.shape[:2]
                else:
                    # Use raw camera frame if no card detected
                    self.card_detected = False
                    display_frame = frame
                    h, w = frame.shape[:2]
                
                # Convert frame for display
                frame_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                
                # Draw ROI rectangle on the displayed frame
                x1 = int(w * self.roi[0])
                y1 = int(h * self.roi[1])
                x2 = int(w * self.roi[2])
                y2 = int(h * self.roi[3])
                
                # Draw red rectangle for ROI
                cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), (255, 0, 0), 2)
                
                # Add text label
                cv2.putText(frame_rgb, "OCR Region", (x1, max(y1-10, 15)), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                
                # Resize for display (fit to 640x480 preview)
                display_h, display_w = 480, 640
                if h != display_h or w != display_w:
                    frame_rgb = cv2.resize(frame_rgb, (display_w, display_h))
                
                # Convert to PhotoImage
                img = Image.fromarray(frame_rgb)
                photo = ImageTk.PhotoImage(img)
                
                # Update GUI
                self.root.after(0, lambda p=photo: self._update_frame(p))
                
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"ERROR: {str(e)}"))
    
    def _update_frame(self, photo):
        """Update the preview frame in the GUI"""
        if self.running:
            self.preview_label.config(image=photo)
            self.preview_label.image = photo
            
            self.frame_var.set(str(self.frame_count))
            
            if self.card_detected:
                self.card_var.set("✓ Detected")
                self.card_label.config(foreground="green")
            else:
                self.card_var.set("Not detected")
                self.card_label.config(foreground="red")


def main():
    root = tk.Tk()
    app = CameraPreview(root, camera_idx=0, resolution=(640, 480))
    root.mainloop()


if __name__ == "__main__":
    main()
