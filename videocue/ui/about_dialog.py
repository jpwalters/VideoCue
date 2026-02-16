"""
About dialog for VideoCue application
"""

from PyQt6.QtCore import Qt  # type: ignore
from PyQt6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout  # type: ignore

from videocue import __version__


class AboutDialog(QDialog):
    """About dialog showing version info and open source components"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About VideoCue")
        self.setMinimumSize(600, 200)

        layout = QVBoxLayout(self)

        # App info header (static, no scrolling)
        info_text = QTextBrowser()
        info_text.setReadOnly(True)
        info_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        info_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        info_text.document().setIndentWidth(0)

        info_html = f"""<h2 style="margin: 0; padding: 0;">VideoCue - Multi-camera PTZ Controller</h2>
<p style="margin: 5px 0; padding: 0;"><b>Version {__version__}</b></p>
<p style="margin: 5px 0; padding: 0;">Controls professional PTZ cameras using VISCA-over-IP protocol with NDI video streaming support.</p>
<p style="margin: 5px 0; padding: 0;"><a href="https://github.com/jpwalters/VideoCue">https://github.com/jpwalters/VideoCue</a></p>

<hr style="margin: 8px 0;">

<p style="font-size: 9pt; color: #888; margin: 5px 0; padding: 0;">
VideoCue is free and open source software. This application is provided "as is" without warranty of any kind.
See the LICENSE file for full terms.
</p>
"""

        info_text.setHtml(info_html)
        info_text.setOpenExternalLinks(True)
        layout.addWidget(info_text)

        # Scrollable components list
        components_text = QTextBrowser()
        components_text.setReadOnly(True)

        components_html = """<h3 style="margin-top: 0;">Open Source Components</h3>

<p><b>Python</b> - PSF License<br>
The Python programming language<br>
<a href="https://www.python.org/">https://www.python.org/</a></p>

<p><b>PyQt6</b> - GPL v3 / Commercial License<br>
Python bindings for Qt6 GUI framework<br>
<a href="https://www.riverbankcomputing.com/software/pyqt/">https://www.riverbankcomputing.com/software/pyqt/</a></p>

<p><b>pygame</b> - LGPL License<br>
Game controller and input library<br>
<a href="https://www.pygame.org/">https://www.pygame.org/</a></p>

<p><b>qdarkstyle</b> - MIT License<br>
Dark theme stylesheet for Qt applications<br>
<a href="https://github.com/ColinDuquesnoy/QDarkStyleSheet">https://github.com/ColinDuquesnoy/QDarkStyleSheet</a></p>

<p><b>numpy</b> - BSD License<br>
Numerical computing library for Python<br>
<a href="https://numpy.org/">https://numpy.org/</a></p>

<p><b>ndi-python</b> (Optional) - MIT License<br>
Python bindings for NewTek NDI SDK<br>
<a href="https://github.com/buresu/ndi-python">https://github.com/buresu/ndi-python</a></p>

<p><b>NDI SDK</b> (Optional) - NewTek NDI License<br>
Network Device Interface SDK for video streaming<br>
<a href="https://ndi.tv/">https://ndi.tv/</a></p>
"""

        components_text.setHtml(components_html)
        components_text.setOpenExternalLinks(True)
        layout.addWidget(components_text)
