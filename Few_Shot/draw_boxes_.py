import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image, ImageTk
import os
import json
from collections import Counter

# --- Configuration ---
IMAGE_DISPLAY_SIZE = (500, 500)
ANNOTATIONS_FILE = "annotations.json"
PROGRESS_FILE = "progress.json"
ANNOTATION_TYPES_FILE = "annotation_types.json"
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
        self.annotation_type_var = tk.StringVar()
        self.drawn_bbox_ids_on_canvas = {}
        self.current_subfolder_active_annotations = {}
        self.canvas_drawing_state = {}
        self.undo_stack = []
        self.unsaved_changes = False

        # --- UI Elements ---
        self.image_canvases = []
        self.overall_canvas = None
        self.inner_image_grid_frame = None
        self.annotation_type_frame = None
        self.counts_frame = None
        self.annotation_type_combo = None
        self.count_labels = {}
        self.annotation_types = []
        self.status_bar_label = tk.Label(self.root, text="Status: Initializing...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        
        # --- Initialization ---
        self._load_annotation_types()
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
        self.btn_undo = tk.Button(controls_frame, text="Undo (Ctrl+Z)", command=self._action_undo_last_bbox, width=15)
        self.btn_undo.pack(side=tk.LEFT, padx=5, pady=5)
        self.btn_prev = tk.Button(controls_frame, text="Previous (Ctrl+Left)", command=self._action_previous_subfolder, width=20)
        self.btn_prev.pack(side=tk.LEFT, padx=5, pady=5)
        
        top_info_frame = tk.Frame(main_frame)
        top_info_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        self.annotation_type_frame = tk.LabelFrame(top_info_frame, text="Type of Annotation")
        self.annotation_type_frame.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.counts_frame = tk.LabelFrame(top_info_frame, text="Annotation Counts")
        self.counts_frame.pack(side=tk.RIGHT, padx=5, fill=tk.Y)
        
        self._rebuild_annotation_widgets()

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
        self.inner_image_grid_frame = tk.Frame(self.overall_canvas)
        self.overall_canvas.create_window((0, 0), window=self.inner_image_grid_frame, anchor="nw")
        self.image_canvases = []
        for i in range(4):
            row, col = divmod(i, 2)
            canvas = tk.Canvas(self.inner_image_grid_frame, bg="gray", relief=tk.RIDGE, borderwidth=1, width=IMAGE_DISPLAY_SIZE[0], height=IMAGE_DISPLAY_SIZE[1])
            canvas.grid(row=row, column=col, padx=5, pady=5)
            self.image_canvases.append(canvas)
            self.canvas_drawing_state[canvas] = {}
            canvas.bind("<ButtonPress-1>", lambda event, c=canvas: self._on_canvas_press(event, c))
            canvas.bind("<B1-Motion>", lambda event, c=canvas: self._on_canvas_drag(event, c))
            canvas.bind("<ButtonRelease-1>", lambda event, c=canvas: self._on_canvas_release(event, c))
        scroll_widgets = [self.overall_canvas, self.inner_image_grid_frame] + self.image_canvases
        for widget in scroll_widgets:
            widget.bind("<MouseWheel>", self._on_mouse_wheel_scroll)

    def _rebuild_annotation_widgets(self):
        for widget in self.annotation_type_frame.winfo_children():
            widget.destroy()
        for widget in self.counts_frame.winfo_children():
            widget.destroy()

        self.annotation_type_combo = ttk.Combobox(
            self.annotation_type_frame,
            textvariable=self.annotation_type_var,
            state='readonly',
            height=15
        )
        display_types = [t for t in self.annotation_types if t != 'other']
        self.annotation_type_combo['values'] = display_types
        if display_types and not self.annotation_type_var.get():
             self.annotation_type_var.set(display_types[0])
        self.annotation_type_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.annotation_type_combo.bind("<<ComboboxSelected>>", self._on_annotation_type_select)
        
        add_new_btn = tk.Button(self.annotation_type_frame, text="Add New...", command=self._add_new_annotation_type)
        add_new_btn.pack(side=tk.LEFT, padx=(0, 5), pady=5)

        self.count_labels = {}
        for type_name in display_types:
            frame = tk.Frame(self.counts_frame)
            frame.pack(side=tk.TOP, fill=tk.X, anchor='w')
            label = tk.Label(frame, text=f"{type_name.title()}:", anchor='w')
            label.pack(side=tk.LEFT, padx=2, pady=2)
            count_label = tk.Label(frame, text="0", width=4, anchor='e')
            count_label.pack(side=tk.RIGHT, padx=2, pady=2)
            self.count_labels[type_name] = count_label
        
        self._update_annotation_counts()

    def _on_annotation_type_select(self, event=None):
        self.unsaved_changes = True
        self._update_status(f"Annotation type changed to '{self.annotation_type_var.get()}'. Remember to save.")

    def _add_new_annotation_type(self):
        new_type = simpledialog.askstring("New Annotation Type", "Enter the name for the new annotation type:", parent=self.root)

        if not new_type or not new_type.strip():
            self._update_status("New type creation cancelled or empty.")
            return

        new_type = new_type.lower().strip()
        
        if new_type in self.annotation_types:
            self.annotation_type_var.set(new_type)
            messagebox.showinfo("Already Exists", f"The type '{new_type.title()}' already exists. It has been selected for you.")
            return

        try:
            other_index = self.annotation_types.index("other")
            self.annotation_types.insert(other_index, new_type)
        except ValueError:
            self.annotation_types.append(new_type)

        self._save_annotation_types()
        self._rebuild_annotation_widgets()
        self.annotation_type_var.set(new_type)
        self.unsaved_changes = True
        self._update_status(f"Added new annotation type '{new_type}'. Set as current type.")

    def _on_mouse_wheel_scroll(self, event):
        if event.state & 0x0001:
            self.overall_canvas.xview_scroll(-1 * (event.delta // 120), "units")
        else:
            self.overall_canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _setup_keyboard_shortcuts(self):
        self.root.bind("<Control-s>", lambda event: self._action_save_annotations())
        self.root.bind("<Control-d>", lambda event: self._action_clear_current_annotations())
        self.root.bind("<Control-z>", lambda event: self._action_undo_last_bbox())
        self.root.bind("<Control-Right>", lambda event: self._action_save_and_next())
        self.root.bind("<Control-Left>", lambda event: self._action_previous_subfolder())

    def _load_initial_state(self):
        self._update_status("Select the main folder containing your image subfolders.")
        self.main_folder_path = filedialog.askdirectory(title="Select Main Folder Containing Subfolders")
        if not self.main_folder_path:
            self.root.destroy()
            return
        
        self._discover_subfolders()
        if not self.subfolders:
            messagebox.showinfo("Info", "No subfolders found.")
            self._update_button_states()
            return

        self._load_annotations_from_file()
        self._load_progress_from_file()

        start_index = 0
        completed = self.progress_data.get("completed_subfolders", [])
        for i, folder in enumerate(self.subfolders):
            if folder not in completed:
                start_index = i
                break
        else:
            start_index = max(0, len(self.subfolders) - 1)
            if self.subfolders:
                self._update_status("All subfolders are completed. Loading last one for review.")

        if self.subfolders:
            self._load_subfolder_by_index(start_index)
        self._update_button_states()

    def _discover_subfolders(self):
        try:
            self.subfolders = sorted([d for d in os.listdir(self.main_folder_path) if os.path.isdir(os.path.join(self.main_folder_path, d))])
            self._update_status(f"Found {len(self.subfolders)} subfolders.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not read subfolders: {e}")

    def _clear_display_and_current_data(self):
        for i, canvas in enumerate(self.image_canvases):
            canvas.delete("all")
            canvas.config(bg="gray")
            self.current_photo_images[i] = None
            self.current_pil_images[i] = None
            self.current_image_names[i] = None
        self.drawn_bbox_ids_on_canvas.clear()
        self.current_subfolder_active_annotations.clear()
        self.undo_stack.clear()
        self.unsaved_changes = False

    def _load_subfolder_by_index(self, idx):
        if not (0 <= idx < len(self.subfolders)):
            messagebox.showinfo("Info", "You have reached the beginning or end of the subfolders.")
            return

        self._clear_display_and_current_data()
        self.current_subfolder_index = idx
        self.current_subfolder_name = self.subfolders[idx]
        full_path = os.path.join(self.main_folder_path, self.current_subfolder_name)
        
        completed_status = "(Completed)" if self.current_subfolder_name in self.progress_data.get("completed_subfolders", []) else ""
        self.root.title(f"Annotator - {self.current_subfolder_name} {completed_status} ({idx + 1}/{len(self.subfolders)})")
        
        image_files = sorted([f for f in os.listdir(full_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])

        subfolder_data = self.annotations_data.get(self.current_subfolder_name, {})
        annotation_type = subfolder_data.get("type_of_annotation", self.annotation_type_combo.get())
        
        combo_values = self.annotation_type_combo['values']
        if annotation_type not in combo_values:
             annotation_type = combo_values[0] if combo_values else ""
        self.annotation_type_var.set(annotation_type)

        for i in range(4):
            if i < len(image_files):
                img_name = image_files[i]
                img_path = os.path.join(full_path, img_name)
                canvas = self.image_canvases[i]
                try:
                    img = Image.open(img_path).resize(IMAGE_DISPLAY_SIZE, Image.LANCZOS)
                    self.current_pil_images[i] = img
                    self.current_photo_images[i] = ImageTk.PhotoImage(img)
                    self.current_image_names[i] = img_name
                    canvas.create_image(0, 0, anchor=tk.NW, image=self.current_photo_images[i])
                    self.canvas_drawing_state[canvas] = {'image_name': img_name}
                    
                    annotations = subfolder_data.get("annotations", {})
                    self.current_subfolder_active_annotations[img_name] = annotations.get(img_name, []).copy()
                    self.drawn_bbox_ids_on_canvas[img_name] = []
                    for bbox in self.current_subfolder_active_annotations[img_name]:
                        rect_id = canvas.create_rectangle(bbox, outline=BBOX_COLOR, width=BBOX_WIDTH)
                        self.drawn_bbox_ids_on_canvas[img_name].append(rect_id)
                except Exception as e:
                    canvas.create_text(IMAGE_DISPLAY_SIZE[0]/2, IMAGE_DISPLAY_SIZE[1]/2, text=f"Error loading\n{img_name}", fill="red", justify=tk.CENTER)
            else:
                self.image_canvases[i].create_text(IMAGE_DISPLAY_SIZE[0]/2, IMAGE_DISPLAY_SIZE[1]/2, text="No Image", fill="black")
        
        self.unsaved_changes = False
        self._update_button_states()

    def _update_button_states(self):
        has_subfolders = bool(self.subfolders)
        self.btn_save.config(state=tk.NORMAL if has_subfolders else tk.DISABLED)
        self.btn_clear.config(state=tk.NORMAL if has_subfolders else tk.DISABLED)
        can_go_next = self.current_subfolder_index < len(self.subfolders) - 1
        can_go_prev = self.current_subfolder_index > 0
        self.btn_save_next.config(state=tk.NORMAL if can_go_next else tk.DISABLED)
        self.btn_prev.config(state=tk.NORMAL if can_go_prev else tk.DISABLED)
        self.btn_undo.config(state=tk.NORMAL if self.undo_stack else tk.DISABLED)

    def _on_canvas_press(self, event, canvas):
        state = self.canvas_drawing_state.get(canvas)
        if not state or not state.get('image_name'): return
        state['start_x'] = canvas.canvasx(event.x)
        state['start_y'] = canvas.canvasy(event.y)
        state['active_rect_id'] = canvas.create_rectangle(state['start_x'], state['start_y'], state['start_x'], state['start_y'], outline=BBOX_COLOR, width=BBOX_WIDTH, dash=(4, 2))

    def _on_canvas_drag(self, event, canvas):
        state = self.canvas_drawing_state.get(canvas)
        if not state or not state.get('active_rect_id'): return
        cur_x, cur_y = canvas.canvasx(event.x), canvas.canvasy(event.y)
        canvas.coords(state['active_rect_id'], state['start_x'], state['start_y'], cur_x, cur_y)

    def _on_canvas_release(self, event, canvas):
        state = self.canvas_drawing_state.get(canvas)
        if not state or not state.get('active_rect_id'): return
        
        canvas.delete(state['active_rect_id'])
        state['active_rect_id'] = None
        
        x1, y1 = state['start_x'], state['start_y']
        x2, y2 = canvas.canvasx(event.x), canvas.canvasy(event.y)
        bbox = [int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2))]

        if bbox[2] - bbox[0] < 5 or bbox[3] - bbox[1] < 5: return

        img_name = state['image_name']
        self.current_subfolder_active_annotations.setdefault(img_name, []).append(bbox)
        rect_id = canvas.create_rectangle(bbox, outline=BBOX_COLOR, width=BBOX_WIDTH)
        self.drawn_bbox_ids_on_canvas.setdefault(img_name, []).append(rect_id)
        self.undo_stack.append((canvas, img_name))
        
        self.unsaved_changes = True
        self._update_button_states()

    def _action_save_annotations(self, called_from_next=False):
        if not self.current_subfolder_name: return False

        # --- FIX: Use .copy() to prevent overwriting saved data ---
        # By creating a shallow copy, we ensure that the dictionary stored in
        # self.annotations_data is a separate object from the one being actively
        # used and cleared (self.current_subfolder_active_annotations).
        self.annotations_data[self.current_subfolder_name] = {
            "type_of_annotation": self.annotation_type_var.get(),
            "annotations": self.current_subfolder_active_annotations.copy()
        }
        self._write_json_file(ANNOTATIONS_FILE, self.annotations_data)
        
        completed = self.progress_data.setdefault("completed_subfolders", [])
        if self.current_subfolder_name not in completed:
            completed.append(self.current_subfolder_name)
        self._write_json_file(PROGRESS_FILE, self.progress_data)
        
        self.unsaved_changes = False
        self._update_annotation_counts()
        if not called_from_next:
            self._update_status(f"Annotations for {self.current_subfolder_name} saved.")
            self._load_subfolder_by_index(self.current_subfolder_index)
        return True

    def _action_save_and_next(self):
        if self._action_save_annotations(called_from_next=True):
            self._load_subfolder_by_index(self.current_subfolder_index + 1)

    def _action_clear_current_annotations(self):
        if messagebox.askyesno("Confirm Clear", "Clear all boxes for this subfolder?"):
            img_names_to_clear = list(self.current_subfolder_active_annotations.keys())
            for img_name in img_names_to_clear:
                self.current_subfolder_active_annotations[img_name] = []
            
            # Redraw the current subfolder to reflect cleared state
            self._load_subfolder_by_index(self.current_subfolder_index)
            self.unsaved_changes = True

    def _action_undo_last_bbox(self):
        if not self.undo_stack: return
        canvas, img_name = self.undo_stack.pop()
        if self.drawn_bbox_ids_on_canvas.get(img_name):
            rect_id = self.drawn_bbox_ids_on_canvas[img_name].pop()
            canvas.delete(rect_id)
        if self.current_subfolder_active_annotations.get(img_name):
            self.current_subfolder_active_annotations[img_name].pop()
        self.unsaved_changes = True
        self._update_button_states()

    def _action_previous_subfolder(self):
        if self.unsaved_changes and not messagebox.askyesno("Unsaved Changes", "Go to previous without saving?"):
            return
        self._load_subfolder_by_index(self.current_subfolder_index - 1)
        
    def _load_annotation_types(self):
        default_types = ["paragraphs", "tables", "images", "headings", "other"]
        try:
            if os.path.exists(ANNOTATION_TYPES_FILE):
                with open(ANNOTATION_TYPES_FILE, 'r') as f:
                    types = json.load(f)
                    if isinstance(types, list):
                        self.annotation_types = types
                        return
            self.annotation_types = default_types
            self._save_annotation_types()
        except Exception:
            self.annotation_types = default_types

    def _save_annotation_types(self):
        self._write_json_file(ANNOTATION_TYPES_FILE, self.annotation_types)

    def _read_json_file(self, file_path, default_val):
        if not os.path.exists(file_path): return default_val
        try:
            with open(file_path, 'r') as f: return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default_val

    def _load_annotations_from_file(self):
        self.annotations_data = self._read_json_file(ANNOTATIONS_FILE, {})
        self._update_annotation_counts()

    def _load_progress_from_file(self):
        self.progress_data = self._read_json_file(PROGRESS_FILE, {"completed_subfolders": []})

    def _write_json_file(self, file_path, data):
        try:
            with open(file_path, 'w') as f: json.dump(data, f, indent=4)
        except IOError as e:
            messagebox.showerror("Error", f"Could not save to {file_path}: {e}")

    def _update_annotation_counts(self):
        if not hasattr(self, 'count_labels'): return # Guard against early calls
        counts = Counter(v.get("type_of_annotation") for v in self.annotations_data.values() if v.get("type_of_annotation"))
        for type_name, label in self.count_labels.items():
            label.config(text=str(counts.get(type_name, 0)))

    def _on_app_close(self):
        if self.unsaved_changes:
            choice = ExitDialog(self.root).get_choice()
            if choice == "save_exit":
                if self._action_save_annotations():
                    self.root.destroy()
            elif choice == "exit_no_save":
                self.root.destroy()
            # if "cancel", do nothing
        else:
            self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AnnotationApp(root)
    root.mainloop()