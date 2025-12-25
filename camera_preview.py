#!/usr/bin/env python3
"""
Simple camera preview GUI for checking camera placement
Shows live camera feed with card detection outline
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
        self.root.geometry("800x600")
        
        self.camera_idx = camera_idx
        self.resolution = resolution
        self.cap = None
        self.running = False
        self.frame_count = 0
        
        # Create GUI
        self._build_layout()
        
        # Start camera thread
        self.start_preview()
    
    def _build_layout(self):
        """Build the GUI layout"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Camera preview label
        self.preview_label = tk.Label(main_frame, bg="black", width=640, height=480)
        self.preview_label.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Starting camera...")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="blue")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # Info
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(info_frame, text="Frames:").pack(side=tk.LEFT)
        self.frame_var = tk.StringVar(value="0")
        ttk.Label(info_frame, textvariable=self.frame_var).pack(side=tk.LEFT, padx=5)
        
        # Controls
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Close", command=self.stop_preview).pack(side=tk.LEFT)
        
        # Help text
        help_text = (
            "Live camera feed\n"
            "Check if camera is positioned correctly and image is clear"
        )
        help_label = ttk.Label(main_frame, text=help_text, justify=tk.LEFT, foreground="gray")
        help_label.pack(fill=tk.X, pady=10)
    
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
                
                # Resize for display
                h, w = frame_rgb.shape[:2]
                if w > 640 or h > 480:
                    scale = min(640/w, 480/h)
                    new_w, new_h = int(w*scale), int(h*scale)
                    frame_rgb = cv2.resize(frame_rgb, (new_w, new_h))
                
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
