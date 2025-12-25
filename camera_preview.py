#!/usr/bin/env python3
"""
Simple camera preview GUI for checking camera placement
Shows live camera feed with card detection outline
"""

import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from card_sorter.capture import open_camera, detect_card_and_warp
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
        self.card_detected = False
        
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
        
        ttk.Label(info_frame, text="Card detected:").pack(side=tk.LEFT, padx=20)
        self.card_var = tk.StringVar(value="No")
        self.card_label = ttk.Label(info_frame, textvariable=self.card_var, foreground="red")
        self.card_label.pack(side=tk.LEFT, padx=5)
        
        # Controls
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Close", command=self.stop_preview).pack(side=tk.LEFT)
        
        # Help text
        help_text = (
            "Tips for correct camera placement:\n"
            "• Card should fill most of the frame\n"
            "• Card should be straight/perpendicular to camera\n"
            "• Green rectangle shows detected card area\n"
            "• Adjust until 'Card detected: Yes' appears consistently"
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
            self.cap = open_camera(self.resolution, self.camera_idx)
            if not self.cap or not self.cap.isOpened():
                self.root.after(0, lambda: self.status_var.set("ERROR: Camera not found"))
                return
            
            self.root.after(0, lambda: self.status_var.set("Camera ready"))
            
            while self.running:
                ret, frame = self.cap.read()
                if not ret:
                    self.root.after(0, lambda: self.status_var.set("ERROR: Failed to read frame"))
                    break
                
                self.frame_count += 1
                
                # Detect card
                warped = detect_card_and_warp(frame)
                self.card_detected = warped is not None
                
                # Convert frame for display
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Draw card detection box if card detected
                if self.card_detected:
                    # Draw a simple border to show where card was detected
                    h, w = frame.shape[:2]
                    cv2.rectangle(frame_rgb, (10, 10), (w-10, h-10), (0, 255, 0), 3)
                
                # Convert to PhotoImage
                img = Image.fromarray(frame_rgb)
                img.thumbnail((640, 480), Image.Resampling.LANCZOS)
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
                self.card_var.set("Yes ✓")
                self.card_label.config(foreground="green")
                self.status_var.set("Card detected!")
            else:
                self.card_var.set("No")
                self.card_label.config(foreground="red")
                self.status_var.set("Waiting for card...")


def main():
    root = tk.Tk()
    app = CameraPreview(root, camera_idx=0, resolution=(640, 480))
    root.mainloop()


if __name__ == "__main__":
    main()
