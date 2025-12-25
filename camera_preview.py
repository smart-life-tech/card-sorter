#!/usr/bin/env python3
"""
Simple camera preview GUI for checking camera placement
Shows live camera feed with ROI region highlighted
"""

import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
import threading
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from card_sorter.config_loader import AppConfig


class CameraPreview:
    def __init__(self, root, camera_idx=0, resolution=(640, 480)):
        self.root = root
        self.root.title("Camera Preview - Card Sorter")
        self.root.geometry("900x700")
        
        self.camera_idx = camera_idx
        self.resolution = resolution
        self.cap = None
        self.running = False
        self.frame_count = 0
        
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
        ttk.Label(main_frame, text="Live Camera Feed with ROI Region", font=("Arial", 12, "bold")).pack(fill=tk.X)
        
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
        
        # Frame counter
        ttk.Label(status_frame, text="Frames:").pack(side=tk.LEFT, padx=20)
        self.frame_var = tk.StringVar(value="0")
        ttk.Label(status_frame, textvariable=self.frame_var).pack(side=tk.LEFT, padx=5)
        
        # ROI info
        info_frame = ttk.LabelFrame(main_frame, text="Current ROI Settings", padding=5)
        info_frame.pack(fill=tk.X, pady=5)
        
        roi_text = f"ROI: x={self.roi[0]:.0%}-{self.roi[2]:.0%}, y={self.roi[1]:.0%}-{self.roi[3]:.0%}"
        ttk.Label(info_frame, text=roi_text, font=("Courier", 10)).pack(side=tk.LEFT)
        
        ttk.Label(info_frame, text="(Red rectangle on preview)", foreground="red").pack(side=tk.LEFT, padx=10)
        
        # Instructions
        help_frame = ttk.LabelFrame(main_frame, text="Instructions", padding=5)
        help_frame.pack(fill=tk.X, pady=5)
        
        help_text = (
            "The RED RECTANGLE shows what region is being sent to OCR.\n"
            "If it's capturing the wrong area (brown/set symbol), the ROI needs adjustment.\n"
            "Test with wider ROI: python mtg_sorter_cli.py test-ocr-live --roi 0.0 0.0 1.0 1.0\n"
            "This will show what the entire card captures to help calibrate."
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
                
                # Convert frame for display
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Draw ROI rectangle on the frame
                h, w = frame_rgb.shape[:2]
                x1 = int(w * self.roi[0])
                y1 = int(h * self.roi[1])
                x2 = int(w * self.roi[2])
                y2 = int(h * self.roi[3])
                
                # Draw red rectangle for ROI
                cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), (255, 0, 0), 2)
                
                # Add text label
                cv2.putText(frame_rgb, "ROI Region", (x1, y1-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                
                # Resize for display
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
            self.status_var.set("Camera active")


def main():
    root = tk.Tk()
    app = CameraPreview(root, camera_idx=0, resolution=(640, 480))
    root.mainloop()


if __name__ == "__main__":
    main()
