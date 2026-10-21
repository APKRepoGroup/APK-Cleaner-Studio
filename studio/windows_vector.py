"""Bounded VectorDrawable previews using Windows' existing .NET WPF renderer.

No XAML/SVG loader, scripts, external URLs or APK code are executed. Only a
validated geometry scene reaches WPF. Unsupported features fail closed so the
normal package badge remains available. Android continues using its own renderer.
"""
import io
import logging
import math
import os
import re
import threading

NS = "{http://schemas.android.com/apk/res/android}"
TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_WORKER = threading.BoundedSemaphore(1)


def vector_scene(root, resolve_color):
    """Validate before crossing the CLR boundary; resource access stays here."""
    budget = [0, 0]

    def attr(node, key, default=None):
        return node.get(NS + key, default)

    def number(node, key, default, minimum=-100_000, maximum=100_000):
        value = float(attr(node, key, str(default)))
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError("Invalid vector number")
        return value

    def path(node):
        value = attr(node, "pathData", "")
        budget[1] += len(value)
        if not value or len(value) > 32768 or budget[1] > 65536:
            raise ValueError("Vector path budget")
        tokens = TOKEN.findall(value)
        if re.sub(r"[\s,]", "", TOKEN.sub("", value)) or not tokens or tokens[0] not in ("m", "M"):
            raise ValueError("Invalid vector path")
        for token in tokens:
            if len(token) > 1 or token not in "MmLlHhVvCcSsQqTtAaZz":
                parsed = float(token)
                if not math.isfinite(parsed) or abs(parsed) > 100_000:
                    raise ValueError("Invalid vector coordinate")
        # WPF's grammar also accepts non-SVG constructs; the tokenizer above
        # deliberately permits only Android/SVG path commands and finite numbers.
        return " ".join(tokens)

    def fill_rule(node):
        value = attr(node, "fillType", "nonZero")
        if value not in {"nonZero", "evenOdd", "0", "1"}:
            raise ValueError("Unsupported fill rule")
        return value in {"evenOdd", "1"}

    def paint(node, key, alpha_key):
        value = attr(node, key)
        rgba = resolve_color(value) if value is not None else (0, 0, 0, 0)
        alpha = number(node, alpha_key, 1, 0, 1)
        return (*rgba[:3], round(rgba[3] * alpha))

    def children(node, depth=0):
        if depth > 8:
            raise ValueError("Vector nesting limit")
        result = []
        for child in node:
            budget[0] += 1
            if budget[0] > 64:
                raise ValueError("Vector node limit")
            if child.tag == "group":
                result.append({"kind": "group", "transform": tuple(number(child, key, default) for key, default in (
                    ("pivotX", 0), ("pivotY", 0), ("scaleX", 1), ("scaleY", 1),
                    ("rotation", 0), ("translateX", 0), ("translateY", 0))), "children": children(child, depth + 1)})
            elif child.tag in {"path", "clip-path"}:
                if len(child):
                    raise ValueError("Gradient vectors are not supported")
                item = {"kind": child.tag, "path": path(child), "even_odd": fill_rule(child)}
                if child.tag == "path":
                    # Do not silently render a partial path as a complete path.
                    for key, default in (("trimPathStart", 0), ("trimPathEnd", 1), ("trimPathOffset", 0)):
                        if number(child, key, default) != default:
                            raise ValueError("Trimmed vector paths are not supported")
                    cap, join = attr(child, "strokeLineCap", "butt"), attr(child, "strokeLineJoin", "miter")
                    if cap not in {"butt", "round", "square", "0", "1", "2"} or join not in {"miter", "round", "bevel", "0", "1", "2"}:
                        raise ValueError("Unsupported vector stroke")
                    item.update(fill=paint(child, "fillColor", "fillAlpha"), stroke=paint(child, "strokeColor", "strokeAlpha"),
                                width=number(child, "strokeWidth", 0, 0, 4096), cap=cap, join=join,
                                miter=number(child, "strokeMiterLimit", 4, 1, 1000))
                result.append(item)
            else:
                raise ValueError("Unsupported vector element")
        return result

    if root.tag != "vector" or attr(root, "tint") is not None or attr(root, "autoMirrored", "false") not in {"false", "0"}:
        raise ValueError("Unsupported vector root")
    return {"width": number(root, "viewportWidth", 0, .001, 4096),
            "height": number(root, "viewportHeight", 0, .001, 4096),
            "alpha": number(root, "alpha", 1, 0, 1), "children": children(root)}


def _render(scene, size):
    import clr
    for assembly in ("WindowsBase", "PresentationCore"):
        clr.AddReference(assembly + ", Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35")
    from System.IO import MemoryStream
    from System.Windows.Media import (DrawingVisual, Geometry, PathGeometry, FillRule, Matrix, MatrixTransform,
                                      ScaleTransform, SolidColorBrush, Color, Pen, PenLineCap, PenLineJoin, PixelFormats)
    from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame

    def brush(rgba):
        return SolidColorBrush(Color.FromArgb(rgba[3], rgba[0], rgba[1], rgba[2])) if rgba[3] else None

    visual = DrawingVisual()
    context = visual.RenderOpen()

    def draw(items):
        clips = 0
        try:
            for item in items:
                if item["kind"] == "group":
                    px, py, sx, sy, rotation, tx, ty = item["transform"]
                    matrix = Matrix.Identity
                    matrix.Translate(-px, -py)
                    matrix.Scale(sx, sy)
                    matrix.Rotate(rotation)
                    matrix.Translate(px + tx, py + ty)
                    context.PushTransform(MatrixTransform(matrix))
                    try:
                        draw(item["children"])
                    finally:
                        context.Pop()
                    continue
                geometry = PathGeometry.CreateFromGeometry(Geometry.Parse(item["path"]))
                geometry.FillRule = FillRule.EvenOdd if item["even_odd"] else FillRule.Nonzero
                if item["kind"] == "clip-path":
                    context.PushClip(geometry)
                    clips += 1
                else:
                    stroke = brush(item["stroke"])
                    pen = Pen(stroke, item["width"]) if stroke is not None and item["width"] else None
                    if pen is not None:
                        pen.StartLineCap = pen.EndLineCap = {"butt": PenLineCap.Flat, "0": PenLineCap.Flat,
                            "round": PenLineCap.Round, "1": PenLineCap.Round, "square": PenLineCap.Square, "2": PenLineCap.Square}[item["cap"]]
                        pen.LineJoin = {"miter": PenLineJoin.Miter, "0": PenLineJoin.Miter, "round": PenLineJoin.Round,
                                        "1": PenLineJoin.Round, "bevel": PenLineJoin.Bevel, "2": PenLineJoin.Bevel}[item["join"]]
                        pen.MiterLimit = item["miter"]
                    context.DrawGeometry(brush(item["fill"]), pen, geometry)
        finally:
            for _ in range(clips):
                context.Pop()

    try:
        context.PushTransform(ScaleTransform(size / scene["width"], size / scene["height"]))
        context.PushOpacity(scene["alpha"])
        draw(scene["children"])
        context.Pop()
        context.Pop()
    finally:
        context.Close()
    bitmap = RenderTargetBitmap(size, size, 96, 96, PixelFormats.Pbgra32)
    bitmap.Render(visual)
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    stream = MemoryStream()
    try:
        encoder.Save(stream)
        return bytes(stream.ToArray())
    finally:
        stream.Dispose()


def render_vector(root, resolve_color, size=384):
    """Offscreen STA worker, with a deadline and at most one pending renderer."""
    if os.name != "nt" or not 16 <= size <= 512:
        raise ValueError("Vector renderer unavailable")
    scene = vector_scene(root, resolve_color)
    if not _WORKER.acquire(blocking=False):
        raise ValueError("Vector renderer busy")
    finished, output = threading.Event(), []
    try:
        import clr
        from System.Threading import Thread, ThreadStart, ApartmentState
        def work():
            try:
                output.append(_render(scene, size))
            except Exception:
                logging.getLogger("desktop.icon").debug("Vektör simge oluşturulamadı", exc_info=True)
            finally:
                _WORKER.release()
                finished.set()
        worker = Thread(ThreadStart(work))
        worker.IsBackground = True
        worker.SetApartmentState(ApartmentState.STA)
        worker.Start()
    except Exception:
        _WORKER.release()
        raise ValueError("Vector renderer unavailable") from None
    if not finished.wait(3) or not output:
        raise ValueError("Vector preview unavailable")
    from PIL import Image
    with Image.open(io.BytesIO(output[0])) as image:
        return image.convert("RGBA")
