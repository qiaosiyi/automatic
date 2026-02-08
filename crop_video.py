"""
视频裁剪工具 - GUI 程序
功能：
1. 选择 orgin-video 目录下的视频文件
2. 显示视频第一帧，通过鼠标框取矩形区域
3. 裁剪视频到选定区域，降低帧率为10fps，去除音频
4. 输出到 cropped-video 目录
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import cv2
import threading


class VideoCropApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频裁剪工具 - 红绿灯区域选择")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        # 视频相关变量
        self.video_path = None
        self.first_frame = None          # 原始第一帧 (OpenCV BGR)
        self.display_image = None         # 显示用的缩放图像 (PIL)
        self.tk_image = None              # Tkinter 图像对象
        self.scale_factor = 1.0           # 缩放比例

        # 框选相关变量
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.crop_rect = None             # 在原始图像上的裁剪区域 (x1, y1, x2, y2)

        # 输出目录
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.input_dir = os.path.join(self.script_dir, "orgin-video")
        self.output_dir = os.path.join(self.script_dir, "cropped-video")

        # 构建界面
        self._build_ui()

    def _build_ui(self):
        """构建用户界面"""
        # --- 顶部控制栏 ---
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(control_frame, text="选择视频：").pack(side=tk.LEFT)

        # 获取视频文件列表
        video_files = []
        if os.path.isdir(self.input_dir):
            video_files = sorted([
                f for f in os.listdir(self.input_dir)
                if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
            ])

        self.video_combo = ttk.Combobox(
            control_frame, values=video_files, state="readonly", width=30
        )
        self.video_combo.pack(side=tk.LEFT, padx=(5, 15))
        self.video_combo.bind("<<ComboboxSelected>>", self._on_video_selected)

        self.btn_clear = ttk.Button(
            control_frame, text="清除选区", command=self._clear_selection
        )
        self.btn_clear.pack(side=tk.LEFT, padx=5)

        self.btn_crop = ttk.Button(
            control_frame, text="裁剪并导出", command=self._start_crop, state=tk.DISABLED
        )
        self.btn_crop.pack(side=tk.LEFT, padx=5)

        # 选区信息
        self.info_label = ttk.Label(control_frame, text="请先选择一个视频文件")
        self.info_label.pack(side=tk.LEFT, padx=15)

        # --- 中间画布区域（带滚动条） ---
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 鼠标事件绑定
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # 窗口大小变化时重新绘制
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # --- 底部进度条 ---
        progress_frame = ttk.Frame(self.root, padding=(10, 5))
        progress_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))

        self.progress_label = ttk.Label(progress_frame, text="就绪", width=30)
        self.progress_label.pack(side=tk.RIGHT)

    def _on_video_selected(self, event=None):
        """视频文件被选择时的处理"""
        filename = self.video_combo.get()
        if not filename:
            return

        self.video_path = os.path.join(self.input_dir, filename)
        self._load_first_frame()

    def _load_first_frame(self):
        """加载视频第一帧"""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            messagebox.showerror("错误", f"无法打开视频文件：\n{self.video_path}")
            return

        ret, frame = cap.read()
        cap.release()

        if not ret:
            messagebox.showerror("错误", "无法读取视频第一帧")
            return

        self.first_frame = frame
        self.crop_rect = None
        self.btn_crop.config(state=tk.DISABLED)

        h, w = frame.shape[:2]
        self.info_label.config(text=f"原始分辨率：{w} × {h}  |  请用鼠标框选红绿灯区域")

        self._display_frame()

    def _display_frame(self):
        """将第一帧缩放后显示到画布上"""
        if self.first_frame is None:
            return

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w <= 1 or canvas_h <= 1:
            # 画布尚未渲染，延迟调用
            self.root.after(50, self._display_frame)
            return

        h, w = self.first_frame.shape[:2]

        # 计算缩放比例（适应画布大小）
        scale_w = canvas_w / w
        scale_h = canvas_h / h
        self.scale_factor = min(scale_w, scale_h)

        new_w = int(w * self.scale_factor)
        new_h = int(h * self.scale_factor)

        # 缩放图像
        resized = cv2.resize(self.first_frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self.display_image = Image.fromarray(rgb)
        self.tk_image = ImageTk.PhotoImage(self.display_image)

        # 计算偏移使图像居中
        self.offset_x = (canvas_w - new_w) // 2
        self.offset_y = (canvas_h - new_h) // 2

        # 清除画布并绘制图像
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW,
                                 image=self.tk_image, tags="frame")
        self.rect_id = None

        # 如果已经有选区，重新绘制
        if self.crop_rect is not None:
            self._redraw_rect()

    def _on_canvas_resize(self, event=None):
        """画布大小变化时重新绘制"""
        if self.first_frame is not None:
            self._display_frame()

    def _canvas_to_image(self, cx, cy):
        """画布坐标 -> 原始图像坐标"""
        ix = (cx - self.offset_x) / self.scale_factor
        iy = (cy - self.offset_y) / self.scale_factor
        h, w = self.first_frame.shape[:2]
        ix = max(0, min(ix, w))
        iy = max(0, min(iy, h))
        return int(ix), int(iy)

    def _image_to_canvas(self, ix, iy):
        """原始图像坐标 -> 画布坐标"""
        cx = ix * self.scale_factor + self.offset_x
        cy = iy * self.scale_factor + self.offset_y
        return cx, cy

    def _on_mouse_down(self, event):
        """鼠标按下"""
        if self.first_frame is None:
            return
        self.start_x = event.x
        self.start_y = event.y

        # 删除旧的矩形
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None

    def _on_mouse_drag(self, event):
        """鼠标拖动"""
        if self.first_frame is None or self.start_x is None:
            return

        if self.rect_id:
            self.canvas.delete(self.rect_id)

        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y,
            outline="#00FF00", width=2, dash=(5, 3)
        )

    def _on_mouse_up(self, event):
        """鼠标释放"""
        if self.first_frame is None or self.start_x is None:
            return

        # 转换到原始图像坐标
        x1, y1 = self._canvas_to_image(self.start_x, self.start_y)
        x2, y2 = self._canvas_to_image(event.x, event.y)

        # 确保 x1 < x2, y1 < y2
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        # 检查选区大小
        if (x2 - x1) < 10 or (y2 - y1) < 10:
            self.info_label.config(text="选区太小，请重新框选")
            self.crop_rect = None
            self.btn_crop.config(state=tk.DISABLED)
            return

        self.crop_rect = (x1, y1, x2, y2)
        crop_w = x2 - x1
        crop_h = y2 - y1
        self.info_label.config(
            text=f"选区：({x1}, {y1}) - ({x2}, {y2})  |  尺寸：{crop_w} × {crop_h}"
        )
        self.btn_crop.config(state=tk.NORMAL)

        # 重新绘制精确矩形
        self._redraw_rect()

    def _redraw_rect(self):
        """根据原始图像坐标重新绘制矩形"""
        if self.crop_rect is None:
            return

        if self.rect_id:
            self.canvas.delete(self.rect_id)

        x1, y1, x2, y2 = self.crop_rect
        cx1, cy1 = self._image_to_canvas(x1, y1)
        cx2, cy2 = self._image_to_canvas(x2, y2)

        self.rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline="#00FF00", width=2, dash=(5, 3)
        )

    def _clear_selection(self):
        """清除选区"""
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
        self.crop_rect = None
        self.btn_crop.config(state=tk.DISABLED)
        if self.first_frame is not None:
            h, w = self.first_frame.shape[:2]
            self.info_label.config(text=f"原始分辨率：{w} × {h}  |  请用鼠标框选红绿灯区域")
        else:
            self.info_label.config(text="请先选择一个视频文件")

    def _start_crop(self):
        """开始裁剪（在后台线程中执行）"""
        if self.crop_rect is None or self.video_path is None:
            return

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

        # 禁用按钮
        self.btn_crop.config(state=tk.DISABLED)
        self.btn_clear.config(state=tk.DISABLED)
        self.video_combo.config(state=tk.DISABLED)

        # 后台线程执行裁剪
        thread = threading.Thread(target=self._do_crop, daemon=True)
        thread.start()

    def _do_crop(self):
        """实际执行裁剪操作"""
        x1, y1, x2, y2 = self.crop_rect
        crop_w = x2 - x1
        crop_h = y2 - y1

        # 确保宽高为偶数（视频编码器要求）
        if crop_w % 2 != 0:
            x2 -= 1
            crop_w = x2 - x1
        if crop_h % 2 != 0:
            y2 -= 1
            crop_h = y2 - y1

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            self.root.after(0, lambda: messagebox.showerror("错误", "无法打开视频文件"))
            self._reset_ui()
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        original_fps = cap.get(cv2.CAP_PROP_FPS)
        target_fps = 10

        # 每隔 frame_interval 帧取一帧
        frame_interval = max(1, round(original_fps / target_fps))

        # 输出文件路径
        base_name = os.path.splitext(os.path.basename(self.video_path))[0]
        output_path = os.path.join(self.output_dir, f"{base_name}_cropped.mp4")

        # 使用 mp4v 编码
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(output_path, fourcc, target_fps, (crop_w, crop_h))

        if not writer.isOpened():
            cap.release()
            self.root.after(0, lambda: messagebox.showerror("错误", "无法创建输出视频文件"))
            self._reset_ui()
            return

        self.root.after(0, lambda: self.progress_label.config(
            text=f"正在处理... 原始FPS:{original_fps:.0f} 目标FPS:{target_fps}"
        ))

        frame_idx = 0
        written_frames = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                # 裁剪区域
                cropped = frame[y1:y2, x1:x2]
                writer.write(cropped)
                written_frames += 1

            frame_idx += 1

            # 更新进度条
            if frame_idx % 30 == 0:
                pct = (frame_idx / total_frames) * 100
                self.root.after(0, lambda p=pct, wf=written_frames:
                    self._update_progress(p, wf))

        cap.release()
        writer.release()

        # 完成
        self.root.after(0, lambda: self._on_crop_done(output_path, written_frames))

    def _update_progress(self, pct, written_frames):
        """更新进度条"""
        self.progress['value'] = pct
        self.progress_label.config(text=f"处理中... {pct:.1f}%  已写入 {written_frames} 帧")

    def _on_crop_done(self, output_path, written_frames):
        """裁剪完成回调"""
        self.progress['value'] = 100
        self.progress_label.config(text=f"完成！共写入 {written_frames} 帧 -> {os.path.basename(output_path)}")
        self._reset_ui()
        messagebox.showinfo(
            "裁剪完成",
            f"视频已成功裁剪并保存到：\n{output_path}\n\n"
            f"输出帧数：{written_frames}\n"
            f"帧率：10 FPS\n"
            f"音频：已去除"
        )

    def _reset_ui(self):
        """恢复界面状态"""
        self.btn_crop.config(state=tk.NORMAL if self.crop_rect else tk.DISABLED)
        self.btn_clear.config(state=tk.NORMAL)
        self.video_combo.config(state="readonly")


def main():
    root = tk.Tk()
    app = VideoCropApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
