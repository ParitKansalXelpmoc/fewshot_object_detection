import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk # Added ttk for themed scrollbars
from PIL import Image, ImageTk
import os
import json

# --- Configuration ---
IMAGE_DISPLAY_SIZE = (500, 500) # This is the target size for the image content on each canvas
ANNOTATIONS_FILE = "annotations.json"
PROGRESS_FILE = "progress.json"
BBOX_COLOR = "red"
BBOX_WIDTH = 2

class ExitDialog(tk.Toplevel):
    """Custom dialog for exit confirmation."""
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.title("Confirm Exit")
        self.geometry("380x150") 
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.result = "cancel" 

        label = tk.Label(self, text="You have unsaved annotations.\nDo you want to save before exiting?", pady=10)
        label.pack(pady=10)

        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)

        save_exit_btn = tk.Button(button_frame, text="Save and Exit", command=self._on_save_exit, width=15)
        save_exit_btn.pack(side=tk.LEFT, padx=5)

        exit_no_save_btn = tk.Button(button_frame, text="Exit without Saving", command=self._on_exit_no_save, width=18)
        exit_no_save_btn.pack(side=tk.LEFT, padx=5)

        cancel_btn = tk.Button(button_frame, text="Cancel", command=self._on_cancel, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)

        self.grab_set() 
        self.wait_window()

    def _on_save_exit(self):
        self.result = "save_exit"
        self.destroy()

    def _on_exit_no_save(self):
        self.result = "exit_no_save"
        self.destroy()

    def _on_cancel(self):
        self.result = "cancel"
        self.destroy()

    def get_choice(self):
        return self.result

class AnnotationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Few-Shot Object Detection Annotator")
        self.root.geometry("1100x1150") 
        self.root.minsize(800, 700) 

        # --- Data ---
        self.main_folder_path = ""
        self.subfolders = []
        self.current_subfolder_index = -1
        self.current_subfolder_name = ""
        
        self.annotations_data = {} 
        self.progress_data = {}  

        self.current_pil_images = [None] * 4 
        self.current_photo_images = [None] * 4 
        self.current_image_names = [None] * 4
        self.drawn_bbox_ids_on_canvas = {} 
        self.current_subfolder_active_annotations = {} 
        self.canvas_drawing_state = {}
        
        self.unsaved_changes = False

        # --- UI Elements ---
        self.image_canvases = [] # Will hold the 4 individual tk.Canvas widgets for images
        self.overall_canvas = None # The main scrollable canvas holding the image grid
        self.inner_image_grid_frame = None # Frame inside overall_canvas, holds the 4 image_canvases

        self.status_bar_label = tk.Label(self.root, text="Status: Initializing...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        
        self._setup_ui()
        self._setup_keyboard_shortcuts() 
        self._load_initial_state()
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def _update_status(self, message):
        self.status_bar_label.config(text=f"Status: {message}")
        print(f"Status: {message}") 

    def _setup_ui(self):
        self.status_bar_label.pack(side=tk.BOTTOM, fill=tk.X)

        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        controls_frame = tk.Frame(main_frame) 
        controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0)) 

        self.btn_save = tk.Button(controls_frame, text="Save (Ctrl+S)", command=self._action_save_annotations, width=15) 
        self.btn_save.pack(side=tk.LEFT, padx=5, pady=5)

        self.btn_save_next = tk.Button(controls_frame, text="Save & Next (Ctrl+Right)", command=self._action_save_and_next, width=22) 
        self.btn_save_next.pack(side=tk.LEFT, padx=5, pady=5)

        self.btn_clear = tk.Button(controls_frame, text="Clear Current (Ctrl+D)", command=self._action_clear_current_annotations, width=22) 
        self.btn_clear.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.btn_prev = tk.Button(controls_frame, text="Previous (Ctrl+Left)", command=self._action_previous_subfolder, width=20) 
        self.btn_prev.pack(side=tk.LEFT, padx=5, pady=5)

        # Container for the main scrollable canvas and its scrollbars
        self.overall_canvas_container = tk.Frame(main_frame)
        self.overall_canvas_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 5))

        self.overall_canvas = tk.Canvas(self.overall_canvas_container)
        
        overall_h_scroll = ttk.Scrollbar(self.overall_canvas_container, orient=tk.HORIZONTAL, command=self.overall_canvas.xview)
        overall_v_scroll = ttk.Scrollbar(self.overall_canvas_container, orient=tk.VERTICAL, command=self.overall_canvas.yview)
        
        self.overall_canvas.config(xscrollcommand=overall_h_scroll.set, yscrollcommand=overall_v_scroll.set)
        
        self.overall_canvas.grid(row=0, column=0, sticky="nsew")
        overall_v_scroll.grid(row=0, column=1, sticky="ns")
        overall_h_scroll.grid(row=1, column=0, sticky="ew")
        
        self.overall_canvas_container.grid_rowconfigure(0, weight=1)
        self.overall_canvas_container.grid_columnconfigure(0, weight=1)

        # This frame goes INSIDE the overall_canvas and will hold the 2x2 image canvases
        self.inner_image_grid_frame = tk.Frame(self.overall_canvas)
        self.overall_canvas.create_window((0, 0), window=self.inner_image_grid_frame, anchor="nw", tags="inner_grid_frame_tag")

        self.image_canvases = [] # Initialize list for the four image canvases
        for i in range(4):
            row, col = divmod(i, 2)
            
            # Individual image canvases are children of inner_image_grid_frame
            # They are fixed size based on IMAGE_DISPLAY_SIZE.
            canvas = tk.Canvas(self.inner_image_grid_frame, bg="gray", relief=tk.RIDGE, borderwidth=1,
                               width=IMAGE_DISPLAY_SIZE[0], height=IMAGE_DISPLAY_SIZE[1])
            canvas.grid(row=row, column=col, padx=5, pady=5) 

            self.image_canvases.append(canvas)
            
            # Initialize drawing state for this canvas
            self.canvas_drawing_state[canvas] = {'start_x': 0, 'start_y': 0, 'active_rect_id': None, 'image_name': None}
            # Bind mouse events for drawing bounding boxes
            canvas.bind("<ButtonPress-1>", lambda event, c=canvas: self._on_canvas_press(event, c))
            canvas.bind("<B1-Motion>", lambda event, c=canvas: self._on_canvas_drag(event, c))
            canvas.bind("<ButtonRelease-1>", lambda event, c=canvas: self._on_canvas_release(event, c))
            
            # Set scrollregion for individual canvases to their content size.
            # Since canvas widget size matches IMAGE_DISPLAY_SIZE, no scrollbars are needed for them individually.
            canvas.config(scrollregion=(0, 0, IMAGE_DISPLAY_SIZE[0], IMAGE_DISPLAY_SIZE[1]))

        # Set the scrollregion for the overall_canvas.
        # This requires the inner_image_grid_frame to have its size calculated.
        self.root.update_idletasks() 
        
        required_width = self.inner_image_grid_frame.winfo_reqwidth()
        required_height = self.inner_image_grid_frame.winfo_reqheight()
        self.overall_canvas.config(scrollregion=(0, 0, required_width, required_height))

        # Bind mouse wheel scrolling to the overall_canvas and its relevant children
        scroll_widgets = [self.overall_canvas, self.inner_image_grid_frame] + self.image_canvases
        for widget in scroll_widgets:
            widget.bind("<MouseWheel>", self._on_mouse_wheel_scroll)  # For Windows and macOS
            widget.bind("<Button-4>", self._on_mouse_wheel_scroll)    # For Linux (scroll up)
            widget.bind("<Button-5>", self._on_mouse_wheel_scroll)    # For Linux (scroll down)


    def _on_mouse_wheel_scroll(self, event):
        """Handles mouse wheel scrolling for the main overall_canvas."""
        # Check for Shift key for horizontal scrolling
        # For Windows/macOS, event.delta. For Linux, event.num
        if event.state & 0x0001:  # Shift key is pressed
            if event.delta: # Windows/macOS (event.delta is usually +/-120)
                self.overall_canvas.xview_scroll(-1 * (event.delta // 120), "units")
            elif event.num == 4: # Linux scroll up (becomes left with shift)
                self.overall_canvas.xview_scroll(-1, "units")
            elif event.num == 5: # Linux scroll down (becomes right with shift)
                self.overall_canvas.xview_scroll(1, "units")
        else: # Vertical scroll
            if event.delta: # Windows/macOS
                self.overall_canvas.yview_scroll(-1 * (event.delta // 120), "units")
            elif event.num == 4: # Linux scroll up
                self.overall_canvas.yview_scroll(-1, "units")
            elif event.num == 5: # Linux scroll down
                self.overall_canvas.yview_scroll(1, "units")


    def _setup_keyboard_shortcuts(self):
        self.root.bind("<Control-s>", lambda event: self._action_save_annotations())
        self.root.bind("<Control-S>", lambda event: self._action_save_annotations()) 
        self.root.bind("<Control-Right>", lambda event: self._action_save_and_next())
        self.root.bind("<Control-Left>", lambda event: self._action_previous_subfolder())
        self.root.bind("<Control-d>", lambda event: self._action_clear_current_annotations())
        self.root.bind("<Control-D>", lambda event: self._action_clear_current_annotations()) 
        self._update_status("Keyboard shortcuts active: Ctrl+S (Save), Ctrl+Right (Save & Next), Ctrl+Left (Prev), Ctrl+D (Clear)")


    def _load_initial_state(self):
        self._update_status("Loading initial state...")
        self.main_folder_path = filedialog.askdirectory(title="Select Main Folder Containing Subfolders")
        if not self.main_folder_path:
            self._update_status("No main folder selected. Exiting.")
            messagebox.showerror("Error", "Main folder not selected. Application will now close.")
            self.root.destroy()
            return

        self._update_status(f"Main folder: {self.main_folder_path}")
        self._discover_subfolders()

        if not self.subfolders:
            self._update_status("No subfolders found in the selected main folder.")
            messagebox.showinfo("Info", "No subfolders found. Please select a valid main folder.")
            self._update_button_states() 
            return

        self._load_annotations_from_file()
        self._load_progress_from_file()

        start_index = 0
        if "last_completed_subfolder_name" in self.progress_data:
            last_completed = self.progress_data["last_completed_subfolder_name"]
            try:
                completed_idx = self.subfolders.index(last_completed)
                start_index = completed_idx + 1
                if start_index >= len(self.subfolders):
                    self._update_status("All subfolders appear to be completed. Starting from the last one for review.")
                    start_index = len(self.subfolders) -1 
                    if start_index < 0: start_index = 0 
            except ValueError:
                self._update_status(f"Warning: Last completed subfolder '{last_completed}' not found. Starting from the beginning.")
                start_index = 0
        
        if start_index < len(self.subfolders):
            self._load_subfolder_by_index(start_index)
        elif self.subfolders: 
            self._update_status("All subfolders processed. Loading last subfolder for review or select another.")
            self._load_subfolder_by_index(len(self.subfolders) - 1)
        else:
            self._update_status("No subfolders to load.")
            messagebox.showinfo("Info", "No subfolders available to annotate.")
        
        self._update_button_states()


    def _discover_subfolders(self):
        if not self.main_folder_path or not os.path.isdir(self.main_folder_path):
            self.subfolders = []
            return
        try:
            self.subfolders = sorted([
                d for d in os.listdir(self.main_folder_path)
                if os.path.isdir(os.path.join(self.main_folder_path, d))
            ])
            self._update_status(f"Found {len(self.subfolders)} subfolders.")
        except Exception as e:
            self.subfolders = []
            self._update_status(f"Error discovering subfolders: {e}")
            messagebox.showerror("Error", f"Could not read subfolders: {e}")


    def _clear_display_and_current_data(self):
        for i in range(4):
            canvas = self.image_canvases[i]
            canvas.delete("all") 
            # Reset background and ensure scrollregion matches fixed canvas content size
            canvas.config(bg="gray", scrollregion=(0, 0, IMAGE_DISPLAY_SIZE[0], IMAGE_DISPLAY_SIZE[1]))
            
            self.current_photo_images[i] = None
            self.current_pil_images[i] = None 
            self.current_image_names[i] = None
            
            if canvas in self.canvas_drawing_state: 
                self.canvas_drawing_state[canvas] = {'start_x': 0, 'start_y': 0, 'active_rect_id': None, 'image_name': None}

        self.drawn_bbox_ids_on_canvas.clear() 
        self.current_subfolder_active_annotations.clear()
        self.unsaved_changes = False


    def _load_subfolder_by_index(self, subfolder_idx):
        if not self.subfolders: 
            self._update_status("No subfolders available to load.")
            self._update_button_states()
            return

        if not (0 <= subfolder_idx < len(self.subfolders)):
            self._update_status(f"Subfolder index {subfolder_idx} is out of bounds.")
            if subfolder_idx >= len(self.subfolders):
                messagebox.showinfo("Info", "You have reached the end of the subfolders.")
            else: 
                messagebox.showinfo("Info", "You are at the beginning of the subfolders.")
            self._update_button_states() 
            return

        self._clear_display_and_current_data()
        self.current_subfolder_index = subfolder_idx
        self.current_subfolder_name = self.subfolders[subfolder_idx]
        full_subfolder_path = os.path.join(self.main_folder_path, self.current_subfolder_name)

        self.root.title(f"Annotator - {self.current_subfolder_name} ({self.current_subfolder_index + 1}/{len(self.subfolders)})")
        self._update_status(f"Loading subfolder: {self.current_subfolder_name} ({self.current_subfolder_index + 1}/{len(self.subfolders)})")

        try:
            image_files = sorted([
                f for f in os.listdir(full_subfolder_path)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))
            ])
        except Exception as e:
            self._update_status(f"Error reading images from {self.current_subfolder_name}: {e}")
            messagebox.showerror("Error", f"Could not read images from {self.current_subfolder_name}: {e}")
            self._update_button_states()
            return

        if len(image_files) == 0:
            self._update_status(f"No images found in {self.current_subfolder_name}.")
        
        if len(image_files) != 4 and len(image_files) > 0: 
            self._update_status(f"Warning: Subfolder {self.current_subfolder_name} has {len(image_files)} images, expected 4. Displaying up to 4.")

        subfolder_annotations_from_file = self.annotations_data.get(self.current_subfolder_name, {})

        for i in range(min(len(image_files), 4)): 
            img_name = image_files[i]
            img_path = os.path.join(full_subfolder_path, img_name)
            canvas = self.image_canvases[i]
            
            try:
                img = Image.open(img_path)
                self.current_pil_images[i] = img 
                
                img_resized = img.resize(IMAGE_DISPLAY_SIZE, Image.LANCZOS)
                photo_img = ImageTk.PhotoImage(img_resized)

                self.current_photo_images[i] = photo_img 
                self.current_image_names[i] = img_name
                
                canvas.delete("all") 
                canvas.create_image(0, 0, anchor=tk.NW, image=photo_img, tags="current_image") 
                canvas.config(bg="white") 
                
                # Individual canvas scrollregion is already fixed to IMAGE_DISPLAY_SIZE
                # canvas.config(scrollregion=(0, 0, IMAGE_DISPLAY_SIZE[0], IMAGE_DISPLAY_SIZE[1])) # Redundant if set in _setup_ui & _clear

                self.canvas_drawing_state[canvas]['image_name'] = img_name
                
                self.current_subfolder_active_annotations[img_name] = subfolder_annotations_from_file.get(img_name, []).copy() 
                self.drawn_bbox_ids_on_canvas[img_name] = []

                for bbox in self.current_subfolder_active_annotations[img_name]:
                    rect_id = canvas.create_rectangle(bbox, outline=BBOX_COLOR, width=BBOX_WIDTH)
                    self.drawn_bbox_ids_on_canvas[img_name].append(rect_id)

            except Exception as e:
                self._update_status(f"Error loading image {img_name}: {e}")
                canvas.delete("all")
                # Ensure scrollregion is set correctly for error display
                canvas.config(scrollregion=(0, 0, IMAGE_DISPLAY_SIZE[0], IMAGE_DISPLAY_SIZE[1]), bg="lightgray")
                canvas.create_text(IMAGE_DISPLAY_SIZE[0] // 2, IMAGE_DISPLAY_SIZE[1] // 2, text=f"Error loading\n{img_name}", fill="red", justify=tk.CENTER, anchor=tk.CENTER)
                self.current_image_names[i] = None 
                self.current_pil_images[i] = None
                self.current_photo_images[i] = None

        for i in range(len(image_files), 4): 
            canvas = self.image_canvases[i]
            if self.current_image_names[i] is None: 
                canvas.delete("all")
                canvas.config(scrollregion=(0, 0, IMAGE_DISPLAY_SIZE[0], IMAGE_DISPLAY_SIZE[1]), bg="lightgray")
                canvas.create_text(IMAGE_DISPLAY_SIZE[0] // 2, IMAGE_DISPLAY_SIZE[1] // 2, text="No Image", fill="black", anchor=tk.CENTER)
                
                self.current_pil_images[i] = None
                self.current_photo_images[i] = None
                if canvas in self.canvas_drawing_state:
                    self.canvas_drawing_state[canvas]['image_name'] = None

        self.unsaved_changes = False 
        self._update_button_states()
        
        # Update overall canvas scrollregion in case it's the first load or if somehow it could change
        # (though with fixed size inner elements, it should be constant after _setup_ui)
        self.root.update_idletasks()
        required_width = self.inner_image_grid_frame.winfo_reqwidth()
        required_height = self.inner_image_grid_frame.winfo_reqheight()
        self.overall_canvas.config(scrollregion=(0, 0, required_width, required_height))


    def _update_button_states(self):
        has_subfolders = bool(self.subfolders)
        can_go_next = has_subfolders and self.current_subfolder_index < len(self.subfolders) - 1
        can_go_prev = has_subfolders and self.current_subfolder_index > 0

        self.btn_save.config(state=tk.NORMAL if has_subfolders else tk.DISABLED)
        self.btn_save_next.config(state=tk.NORMAL if can_go_next else tk.DISABLED)
        self.btn_clear.config(state=tk.NORMAL if has_subfolders else tk.DISABLED)
        self.btn_prev.config(state=tk.NORMAL if can_go_prev else tk.DISABLED)

    def _on_canvas_press(self, event, canvas):
        state = self.canvas_drawing_state[canvas]
        if state['image_name'] is None: 
            return
        
        # Coordinates are already relative to the individual canvas content (0,0 of image)
        state['start_x'] = canvas.canvasx(event.x) 
        state['start_y'] = canvas.canvasy(event.y)
        state['active_rect_id'] = canvas.create_rectangle(
            state['start_x'], state['start_y'], state['start_x'], state['start_y'], 
            outline=BBOX_COLOR, width=BBOX_WIDTH, dash=(4, 2)
        )

    def _on_canvas_drag(self, event, canvas):
        state = self.canvas_drawing_state[canvas]
        if state['image_name'] is None or state['active_rect_id'] is None:
            return
        cur_x = canvas.canvasx(event.x)
        cur_y = canvas.canvasy(event.y)
        canvas.coords(state['active_rect_id'], state['start_x'], state['start_y'], cur_x, cur_y)

    def _on_canvas_release(self, event, canvas):
        state = self.canvas_drawing_state[canvas]
        if state['image_name'] is None or state['active_rect_id'] is None:
            return

        canvas.delete(state['active_rect_id'])
        state['active_rect_id'] = None

        end_x = canvas.canvasx(event.x)
        end_y = canvas.canvasy(event.y)
        
        x1 = min(state['start_x'], end_x)
        y1 = min(state['start_y'], end_y)
        x2 = max(state['start_x'], end_x)
        y2 = max(state['start_y'], end_y)

        if abs(x1 - x2) < 5 or abs(y1 - y2) < 5:
            self._update_status("Box too small, not added.")
            return

        img_w, img_h = IMAGE_DISPLAY_SIZE 
        x1 = max(0, min(x1, img_w -1))
        y1 = max(0, min(y1, img_h -1))
        x2 = max(0, min(x2, img_w -1))
        y2 = max(0, min(y2, img_h -1))
        
        if abs(x1 - x2) < 5 or abs(y1 - y2) < 5: 
            self._update_status("Box too small after clamping, not added.")
            return

        bbox_coords = [int(x1), int(y1), int(x2), int(y2)]
        final_rect_id = canvas.create_rectangle(bbox_coords, outline=BBOX_COLOR, width=BBOX_WIDTH)

        current_image_name = state['image_name']
        if current_image_name not in self.current_subfolder_active_annotations:
            self.current_subfolder_active_annotations[current_image_name] = []
        self.current_subfolder_active_annotations[current_image_name].append(bbox_coords)
        
        if current_image_name not in self.drawn_bbox_ids_on_canvas:
            self.drawn_bbox_ids_on_canvas[current_image_name] = []
        self.drawn_bbox_ids_on_canvas[current_image_name].append(final_rect_id)
        
        self.unsaved_changes = True
        self._update_status(f"Added bbox to {current_image_name}: {bbox_coords}")


    def _action_save_annotations(self, called_from_next=False):
        if not self.current_subfolder_name:
            self._update_status("No subfolder loaded to save.")
            return False 

        self.annotations_data[self.current_subfolder_name] = self.current_subfolder_active_annotations.copy() 
        self._write_json_file(ANNOTATIONS_FILE, self.annotations_data)
        
        self.progress_data["last_completed_subfolder_name"] = self.current_subfolder_name
        self._write_json_file(PROGRESS_FILE, self.progress_data)
        
        self.unsaved_changes = False
        if not called_from_next: 
            self._update_status(f"Annotations for {self.current_subfolder_name} saved.")
        return True 

    def _action_save_and_next(self):
        if self._action_save_annotations(called_from_next=True): 
            self._update_status(f"Annotations for {self.current_subfolder_name} saved. Moving to next.")
            if self.current_subfolder_index < len(self.subfolders) - 1:
                self._load_subfolder_by_index(self.current_subfolder_index + 1)
            else:
                self._update_status("All subfolders annotated!")
                messagebox.showinfo("Info", "You have reached the end of the subfolders.")
                self._update_button_states() 
        else:
            self._update_status("Could not save, cannot move to next.")


    def _action_clear_current_annotations(self):
        if not self.current_subfolder_name:
            self._update_status("No subfolder loaded to clear.")
            return

        is_anything_to_clear = False
        for img_name_key in self.current_subfolder_active_annotations:
            if img_name_key in self.current_image_names and self.current_subfolder_active_annotations[img_name_key]:
                is_anything_to_clear = True
                break
        
        if not is_anything_to_clear:
            for i, canvas in enumerate(self.image_canvases):
                img_name = self.current_image_names[i]
                if img_name and img_name in self.drawn_bbox_ids_on_canvas and self.drawn_bbox_ids_on_canvas[img_name]:
                    is_anything_to_clear = True
                    break
            
        if not is_anything_to_clear:
            self._update_status(f"No annotations to clear for {self.current_subfolder_name}.")
            return

        if messagebox.askyesno("Confirm Clear", f"Are you sure you want to clear all annotations for subfolder '{self.current_subfolder_name}'? This action cannot be undone until next save."):
            for i, canvas in enumerate(self.image_canvases):
                img_name = self.current_image_names[i] 
                if img_name: 
                    if img_name in self.drawn_bbox_ids_on_canvas:
                        for rect_id in self.drawn_bbox_ids_on_canvas[img_name]:
                            canvas.delete(rect_id) 
                        self.drawn_bbox_ids_on_canvas[img_name] = []
                    
                    if img_name in self.current_subfolder_active_annotations: 
                        self.current_subfolder_active_annotations[img_name] = []
            
            self.unsaved_changes = True 
            self._update_status(f"Cleared annotations for {self.current_subfolder_name}. Save to persist this.")

    def _action_previous_subfolder(self):
        if self.unsaved_changes:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to proceed to the previous subfolder without saving?"):
                return
        
        if self.current_subfolder_index > 0:
            self._load_subfolder_by_index(self.current_subfolder_index - 1)
        else:
            self._update_status("Already at the first subfolder.")
            messagebox.showinfo("Info", "You are at the first subfolder.")
        self._update_button_states()


    def _load_annotations_from_file(self):
        try:
            if os.path.exists(ANNOTATIONS_FILE):
                with open(ANNOTATIONS_FILE, 'r') as f:
                    self.annotations_data = json.load(f)
                self._update_status(f"Loaded annotations from {ANNOTATIONS_FILE}")
            else:
                self.annotations_data = {}
                self._update_status(f"{ANNOTATIONS_FILE} not found. Starting fresh.")
        except Exception as e:
            self.annotations_data = {}
            self._update_status(f"Error loading {ANNOTATIONS_FILE}: {e}. Starting fresh.")
            messagebox.showwarning("Warning", f"Could not load annotations file: {e}")

    def _load_progress_from_file(self):
        try:
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE, 'r') as f:
                    self.progress_data = json.load(f)
                self._update_status(f"Loaded progress from {PROGRESS_FILE}")
            else:
                self.progress_data = {}
                self._update_status(f"{PROGRESS_FILE} not found. Starting fresh.")
        except Exception as e:
            self.progress_data = {}
            self._update_status(f"Error loading {PROGRESS_FILE}: {e}. Starting fresh.")
            messagebox.showwarning("Warning", f"Could not load progress file: {e}")

    def _write_json_file(self, filepath, data):
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self._update_status(f"Error saving to {filepath}: {e}")
            messagebox.showerror("Error", f"Could not save to {filepath}: {e}")


    def _on_app_close(self):
        if self.unsaved_changes:
            dialog = ExitDialog(self.root)
            choice = dialog.get_choice()
            if choice == "save_exit":
                self._action_save_annotations()
                self.root.destroy()
            elif choice == "exit_no_save":
                self.root.destroy()
            # else "cancel", do nothing
        else:
            self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = AnnotationApp(root)
    root.mainloop()
