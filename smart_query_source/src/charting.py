from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from typing import List, Dict


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


CHART_TEMPLATES = {
    # 参考 Matplotlib style sheets（dark_background）与 ColorBrewer（BuGn）配色
    "finance_light": {
        "background": "#FFFFFF",
        "axis": "#111827",
        "grid": "#E5E7EB",
        "text": "#111827",
        "bar": "#2F7ED8",
    },
    "dark_background": {
        "background": "#111827",
        "axis": "#E5E7EB",
        "grid": "#374151",
        "text": "#F9FAFB",
        "bar": "#4C78A8",
    },
    "colorbrewer_bugn": {
        "background": "#FFFFFF",
        "axis": "#374151",
        "grid": "#D9F0E5",
        "text": "#111827",
        "bar": "#2CA25F",
    },
}


def _resolve_chart_template():
    name = str(os.getenv("CHART_TEMPLATE", "finance_light") or "finance_light").strip().lower()
    if name not in CHART_TEMPLATES:
        name = "finance_light"
    return name, CHART_TEMPLATES[name]


def save_bar_chart(rows: List[Dict], x_key: str, y_key: str, title: str, out_file: str):
    ensure_dir(os.path.dirname(out_file))
    template_name, theme = _resolve_chart_template()
    xs = []
    for r in rows:
        x = str(r.get(x_key, ""))
        x = x.replace(";", " ").replace(",", "，").replace("'", "''")
        xs.append(x)
    ys = []
    for r in rows:
        try:
            ys.append(float(r.get(y_key, 0) or 0))
        except Exception:
            ys.append(0.0)

    ps_points = ";".join([f"{x},{y}" for x, y in zip(xs, ys)])
    ps_title = title.replace("'", "''")
    ps_out = out_file.replace("'", "''")
    ps_bg = theme["background"]
    ps_axis = theme["axis"]
    ps_grid = theme["grid"]
    ps_text = theme["text"]
    ps_bar = theme["bar"]
    ps_template = template_name.replace("'", "''")
    ps_cmd = rf"""
Add-Type -AssemblyName System.Drawing
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $OutputEncoding
$width = 1280
$height = 720
$bmp = New-Object System.Drawing.Bitmap($width, $height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$bgColor = [System.Drawing.ColorTranslator]::FromHtml('{ps_bg}')
$axisColor = [System.Drawing.ColorTranslator]::FromHtml('{ps_axis}')
$gridColor = [System.Drawing.ColorTranslator]::FromHtml('{ps_grid}')
$textColor = [System.Drawing.ColorTranslator]::FromHtml('{ps_text}')
$barColor = [System.Drawing.ColorTranslator]::FromHtml('{ps_bar}')
$g.Clear($bgColor)

$pairs = '{ps_points}'.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries)
$vals = @()
$labels = @()
foreach ($p in $pairs) {{
  $kv = $p.Split(',')
  if ($kv.Count -ge 2) {{
    $labels += $kv[0]
    $vals += [double]$kv[1]
  }}
}}

$left = 80
$right = 40
$top = 80
$bottom = 180
$plotW = $width - $left - $right
$plotH = $height - $top - $bottom

$axisPen = New-Object System.Drawing.Pen($axisColor, 2)
$gridPen = New-Object System.Drawing.Pen($gridColor, 1)
$g.DrawLine($axisPen, $left, $top + $plotH, $left + $plotW, $top + $plotH)
$g.DrawLine($axisPen, $left, $top, $left, $top + $plotH)

$fontTitle = New-Object System.Drawing.Font("Microsoft YaHei", 18, [System.Drawing.FontStyle]::Bold)
$fontLabel = New-Object System.Drawing.Font("Microsoft YaHei", 10)
$fontValue = New-Object System.Drawing.Font("Microsoft YaHei", 9)
$brushText = New-Object System.Drawing.SolidBrush($textColor)
$brushBar = New-Object System.Drawing.SolidBrush($barColor)

$g.DrawString('{ps_title}  [{ps_template}]', $fontTitle, $brushText, 20, 20)

if ($vals.Count -gt 0) {{
  $maxV = ($vals | Measure-Object -Maximum).Maximum
  if ($maxV -le 0) {{ $maxV = 1.0 }}
  for ($gi = 1; $gi -le 5; $gi++) {{
    $gy = [int]($top + $plotH - ($plotH * $gi / 5.0))
    $g.DrawLine($gridPen, $left, $gy, $left + $plotW, $gy)
  }}
  $n = $vals.Count
  $slotW = [double]$plotW / $n
  $barW = [Math]::Max(8, [int]($slotW * 0.65))
  for ($i = 0; $i -lt $n; $i++) {{
    $v = [double]$vals[$i]
    $h = [int]([Math]::Max(1, ($v / $maxV) * ($plotH - 20)))
    $x = [int]($left + $i * $slotW + (($slotW - $barW) / 2))
    $y = [int]($top + $plotH - $h)
    $g.FillRectangle($brushBar, $x, $y, $barW, $h)
    $valTxt = ("{{0:N0}}" -f $v)
    $g.DrawString($valTxt, $fontValue, $brushText, $x, [Math]::Max(0, $y - 16))
    $lbl = [string]$labels[$i]
    if ($lbl.Length -gt 8) {{ $lbl = $lbl.Substring(0, 8) }}
    $g.DrawString($lbl, $fontLabel, $brushText, $x, $top + $plotH + 8)
  }}
}}

$bmp.Save('{ps_out}', [System.Drawing.Imaging.ImageFormat]::Jpeg)
$axisPen.Dispose()
$gridPen.Dispose()
$fontTitle.Dispose()
$fontLabel.Dispose()
$fontValue.Dispose()
$brushText.Dispose()
$brushBar.Dispose()
$g.Dispose()
$bmp.Dispose()
"""
    try:
        script_path = None
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as tf:
            tf.write(ps_cmd)
            script_path = tf.name
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
            return
    except Exception:
        pass
    finally:
        try:
            if script_path and os.path.exists(script_path):
                os.remove(script_path)
        except Exception:
            pass

    # Fallback: valid tiny JPG placeholder.
    tiny_jpg_b64 = (
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBUQEBAVFQ8VFRUVFRUVFRUVFRUVFRUX"
        "FhUVFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMtNygtLisBCgoKDg0OGhAQGi0lHyUtLS0tLS0t"
        "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBIgACEQED"
        "EQH/xAAXAAADAQAAAAAAAAAAAAAAAAAAAQID/8QAFhEBAQEAAAAAAAAAAAAAAAAAAAER/9oADAMB"
        "AAIRAxEAPwCdAAr/AP/Z"
    )
    with open(out_file, "wb") as f:
        f.write(base64.b64decode(tiny_jpg_b64))
