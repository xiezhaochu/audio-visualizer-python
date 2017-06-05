import sys, io, os, shutil, atexit, string, signal, filecmp
from os.path import expanduser
from queue import Queue
from importlib import import_module
from collections import OrderedDict
from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import QSettings, QModelIndex, Qt
from PyQt4.QtGui import QDesktopServices, QMenu

import preview_thread, core, video_thread

# FIXME: commandline functionality broken until we decide how to implement it
'''
class Command(QtCore.QObject):
  
  videoTask = QtCore.pyqtSignal(str, str, str, list)
  
  def __init__(self):
    QtCore.QObject.__init__(self)
    self.modules = []
    self.selectedComponents = []

    import argparse
    self.parser = argparse.ArgumentParser(description='Create a visualization for an audio file')
    self.parser.add_argument('-i', '--input', dest='input', help='input audio file', required=True)
    self.parser.add_argument('-o', '--output', dest='output', help='output video file', required=True)
    self.parser.add_argument('-b', '--background', dest='bgimage', help='background image file', required=True)
    self.parser.add_argument('-t', '--text', dest='text', help='title text', required=True)
    self.parser.add_argument('-f', '--font', dest='font', help='title font', required=False)
    self.parser.add_argument('-s', '--fontsize', dest='fontsize', help='title font size', required=False)
    self.parser.add_argument('-c', '--textcolor', dest='textcolor', help='title text color in r,g,b format', required=False)
    self.parser.add_argument('-C', '--viscolor', dest='viscolor', help='visualization color in r,g,b format', required=False)
    self.parser.add_argument('-x', '--xposition', dest='xposition', help='x position', required=False)
    self.parser.add_argument('-y', '--yposition', dest='yposition', help='y position', required=False)
    self.parser.add_argument('-a', '--alignment', dest='alignment', help='title alignment', required=False, type=int, choices=[0, 1, 2])
    self.args = self.parser.parse_args()

    self.settings = QSettings('settings.ini', QSettings.IniFormat)
    LoadDefaultSettings(self)
    
    # load colours as tuples from comma-separated strings
    self.textColor = core.Core.RGBFromString(self.settings.value("textColor", '255, 255, 255'))
    self.visColor = core.Core.RGBFromString(self.settings.value("visColor", '255, 255, 255'))
    if self.args.textcolor:
      self.textColor = core.Core.RGBFromString(self.args.textcolor)
    if self.args.viscolor:
      self.visColor = core.Core.RGBFromString(self.args.viscolor)
    
    # font settings
    if self.args.font:
      self.font = QFont(self.args.font)
    else:
      self.font = QFont(self.settings.value("titleFont", QFont()))
    
    if self.args.fontsize:
      self.fontsize = int(self.args.fontsize)
    else:
      self.fontsize = int(self.settings.value("fontSize", 35))
    if self.args.alignment:
      self.alignment = int(self.args.alignment)
    else:
      self.alignment = int(self.settings.value("alignment", 0))

    if self.args.xposition:
      self.textX = int(self.args.xposition)
    else:
      self.textX = int(self.settings.value("xPosition", 70))

    if self.args.yposition:
      self.textY = int(self.args.yposition)
    else:
      self.textY = int(self.settings.value("yPosition", 375))

    ffmpeg_cmd = self.settings.value("ffmpeg_cmd", expanduser("~"))

    self.videoThread = QtCore.QThread(self)
    self.videoWorker = video_thread.Worker(self)

    self.videoWorker.moveToThread(self.videoThread)
    self.videoWorker.videoCreated.connect(self.videoCreated)
    
    self.videoThread.start()
    self.videoTask.emit(self.args.bgimage,
      self.args.text,
      self.font,
      self.fontsize,
      self.alignment,
      self.textX,
      self.textY,
      self.textColor,
      self.visColor,
      self.args.input,
      self.args.output,
      self.selectedComponents)

  def videoCreated(self):
    self.videoThread.quit()
    self.videoThread.wait()
    self.cleanUp()

  def cleanUp(self):
    self.settings.setValue("titleFont", self.font.toString())
    self.settings.setValue("alignment", str(self.alignment))
    self.settings.setValue("fontSize", str(self.fontsize))
    self.settings.setValue("xPosition", str(self.textX))
    self.settings.setValue("yPosition", str(self.textY))
    self.settings.setValue("visColor", '%s,%s,%s' % self.visColor)
    self.settings.setValue("textColor", '%s,%s,%s' % self.textColor)
    sys.exit(0)
'''

class PreviewWindow(QtGui.QLabel):
    def __init__(self, parent, img):
        super(PreviewWindow, self).__init__()
        self.parent = parent
        self.setFrameStyle(QtGui.QFrame.StyledPanel)
        self.pixmap = QtGui.QPixmap(img)

    def paintEvent(self, event):
        size = self.size()
        painter = QtGui.QPainter(self)
        point = QtCore.QPoint(0,0)
        scaledPix = self.pixmap.scaled(size, Qt.KeepAspectRatio, transformMode = Qt.SmoothTransformation)
        # start painting the label from left upper corner
        point.setX((size.width() - scaledPix.width())/2)
        point.setY((size.height() - scaledPix.height())/2)
        #print point.x(), ' ', point.y()
        painter.drawPixmap(point, scaledPix)

    def changePixmap(self, img):
        self.pixmap = QtGui.QPixmap(img)
        self.repaint()

class Main(QtCore.QObject):

  newTask = QtCore.pyqtSignal(list)
  processTask = QtCore.pyqtSignal()
  videoTask = QtCore.pyqtSignal(str, str, list)

  def __init__(self, window):
    QtCore.QObject.__init__(self)

    # print('main thread id: {}'.format(QtCore.QThread.currentThreadId()))
    self.window = window
    self.core = core.Core()
    self.pages = []
    self.selectedComponents = []

    # create data directory, load/create settings
    self.dataDir = QDesktopServices.storageLocation(QDesktopServices.DataLocation)
    self.autosavePath = os.path.join(self.dataDir, 'autosave.avp')
    self.presetDir = os.path.join(self.dataDir, 'presets')
    self.settings = QSettings(os.path.join(self.dataDir, 'settings.ini'), QSettings.IniFormat)
    LoadDefaultSettings(self)
    if not os.path.exists(self.dataDir):
        os.makedirs(self.dataDir)
    for neededDirectory in (self.presetDir, self.settings.value("projectDir")):
        if not os.path.exists(neededDirectory):
            os.mkdir(neededDirectory)

    #
    self.previewQueue = Queue()
    self.previewThread = QtCore.QThread(self)
    self.previewWorker = preview_thread.Worker(self, self.previewQueue)
    self.previewWorker.moveToThread(self.previewThread)
    self.previewWorker.imageCreated.connect(self.showPreviewImage)
    self.previewThread.start()

    self.timer = QtCore.QTimer(self)
    self.timer.timeout.connect(self.processTask.emit)
    self.timer.start(500)

    # begin decorating the window and connecting events
    window.toolButton_selectAudioFile.clicked.connect(self.openInputFileDialog)
    window.toolButton_selectOutputFile.clicked.connect(self.openOutputFileDialog)
    window.progressBar_createVideo.setValue(0)
    window.pushButton_createVideo.clicked.connect(self.createAudioVisualisation)
    window.pushButton_Cancel.clicked.connect(self.stopVideo)
    window.setWindowTitle("Audio Visualizer")

    self.previewWindow = PreviewWindow(self, os.path.join(os.path.dirname(os.path.realpath(__file__)), "background.png"))
    window.verticalLayout_previewWrapper.addWidget(self.previewWindow)
    
    self.modules = self.findComponents()
    self.compMenu = QMenu()
    for i, comp in enumerate(self.modules):
        action = self.compMenu.addAction(comp.Component.__doc__)
        action.triggered[()].connect( lambda item=i: self.insertComponent(item))

    self.window.pushButton_addComponent.setMenu(self.compMenu)
    window.listWidget_componentList.clicked.connect(lambda _: self.changeComponentWidget())
    
    self.window.pushButton_removeComponent.clicked.connect(lambda _: self.removeComponent())

    currentRes = str(self.settings.value('outputWidth'))+'x'+str(self.settings.value('outputHeight'))
    for i, res in enumerate(self.resolutions):
      window.comboBox_resolution.addItem(res)
      if res == currentRes:
        currentRes = i
    window.comboBox_resolution.setCurrentIndex(currentRes)
    window.comboBox_resolution.currentIndexChanged.connect(self.updateResolution)

    self.window.pushButton_listMoveUp.clicked.connect(self.moveComponentUp)
    self.window.pushButton_listMoveDown.clicked.connect(self.moveComponentDown)

    self.window.pushButton_savePreset.clicked.connect(self.openSavePresetDialog)
    self.window.comboBox_openPreset.currentIndexChanged.connect(self.openPreset)
    self.window.pushButton_saveAs.clicked.connect(self.openSaveProjectDialog)
    self.window.pushButton_saveProject.clicked.connect(self.saveCurrentProject)
    self.window.pushButton_openProject.clicked.connect(self.openOpenProjectDialog)
    
    # show the window and load current project
    window.show()
    self.currentProject = self.settings.value("currentProject")
    if self.currentProject and os.path.exists(self.autosavePath) \
        and filecmp.cmp(self.autosavePath, self.currentProject):
        # delete autosave if it's identical to the project
        os.remove(self.autosavePath)
    
    if self.currentProject and os.path.exists(self.autosavePath):
        ch = self.showMessage("Restore unsaved changes in project '%s'?" % os.path.basename(self.currentProject)[:-4], True)
        if ch:
            os.remove(self.currentProject)
            os.rename(self.autosavePath, self.currentProject)
        else:
            os.remove(self.autosavePath)
    
    self.openProject(self.currentProject)
    self.drawPreview()

  def cleanUp(self):
    self.timer.stop()
    self.previewThread.quit()
    self.previewThread.wait()
    self.autosave()
    
  def autosave(self):
    if os.path.exists(self.autosavePath):
        os.remove(self.autosavePath)
    self.createProjectFile(self.autosavePath)

  def openInputFileDialog(self):
    inputDir = self.settings.value("inputDir", expanduser("~"))

    fileName = QtGui.QFileDialog.getOpenFileName(self.window,
       "Open Music File", inputDir, "Music Files (*.mp3 *.wav *.ogg *.flac)");

    if not fileName == "": 
      self.settings.setValue("inputDir", os.path.dirname(fileName))
      self.window.lineEdit_audioFile.setText(fileName)

  def openOutputFileDialog(self):
    outputDir = self.settings.value("outputDir", expanduser("~"))

    fileName = QtGui.QFileDialog.getSaveFileName(self.window,
       "Set Output Video File", outputDir, "Video Files (*.mkv *.mp4)");

    if not fileName == "": 
      self.settings.setValue("outputDir", os.path.dirname(fileName))
      self.window.lineEdit_outputFile.setText(fileName)

  def stopVideo(self):
      print('stop')
      self.videoWorker.cancel()
      self.canceled = True

  def createAudioVisualisation(self):
    # create output video if mandatory settings are filled in
    if self.window.lineEdit_audioFile.text() and self.window.lineEdit_outputFile.text():
        self.canceled = False
        self.progressBarUpdated(-1)
        ffmpeg_cmd = self.settings.value("ffmpeg_cmd", expanduser("~"))
        self.videoThread = QtCore.QThread(self)
        self.videoWorker = video_thread.Worker(self)
        self.videoWorker.moveToThread(self.videoThread)
        self.videoWorker.videoCreated.connect(self.videoCreated)
        self.videoWorker.progressBarUpdate.connect(self.progressBarUpdated)
        self.videoWorker.progressBarSetText.connect(self.progressBarSetText)
        self.videoWorker.imageCreated.connect(self.showPreviewImage)
        self.videoWorker.encoding.connect(self.changeEncodingStatus)
        self.videoThread.start()
        self.videoTask.emit(self.window.lineEdit_audioFile.text(),
          self.window.lineEdit_outputFile.text(),
          self.selectedComponents)
    else:
        self.showMessage("You must select an audio file and output filename.")

  def progressBarUpdated(self, value):
      self.window.progressBar_createVideo.setValue(value)

  def changeEncodingStatus(self, status):
    if status:
      self.window.pushButton_createVideo.setEnabled(False)
      self.window.pushButton_Cancel.setEnabled(True)
      self.window.comboBox_resolution.setEnabled(False)
      self.window.stackedWidget.setEnabled(False)
      self.window.tab_encoderSettings.setEnabled(False)
      self.window.label_audioFile.setEnabled(False)
      self.window.toolButton_selectAudioFile.setEnabled(False)
      self.window.label_outputFile.setEnabled(False)
      self.window.toolButton_selectOutputFile.setEnabled(False)
      self.window.lineEdit_audioFile.setEnabled(False)
      self.window.lineEdit_outputFile.setEnabled(False)
      self.window.pushButton_addComponent.setEnabled(False)
      self.window.pushButton_removeComponent.setEnabled(False)
      self.window.pushButton_listMoveDown.setEnabled(False)
      self.window.pushButton_listMoveUp.setEnabled(False)
      self.window.comboBox_openPreset.setEnabled(False)
      self.window.pushButton_removePreset.setEnabled(False)
      self.window.pushButton_savePreset.setEnabled(False)
      self.window.pushButton_openProject.setEnabled(False)
      self.window.listWidget_componentList.setEnabled(False)
    else:
      self.window.pushButton_createVideo.setEnabled(True)
      self.window.pushButton_Cancel.setEnabled(False)
      self.window.comboBox_resolution.setEnabled(True)
      self.window.stackedWidget.setEnabled(True)
      self.window.tab_encoderSettings.setEnabled(True)
      self.window.label_audioFile.setEnabled(True)
      self.window.toolButton_selectAudioFile.setEnabled(True)
      self.window.lineEdit_audioFile.setEnabled(True)
      self.window.label_outputFile.setEnabled(True)
      self.window.toolButton_selectOutputFile.setEnabled(True)
      self.window.lineEdit_outputFile.setEnabled(True)
      self.window.pushButton_addComponent.setEnabled(True)
      self.window.pushButton_removeComponent.setEnabled(True)
      self.window.pushButton_listMoveDown.setEnabled(True)
      self.window.pushButton_listMoveUp.setEnabled(True)
      self.window.comboBox_openPreset.setEnabled(True)
      self.window.pushButton_removePreset.setEnabled(True)
      self.window.pushButton_savePreset.setEnabled(True)
      self.window.pushButton_openProject.setEnabled(True)
      self.window.listWidget_componentList.setEnabled(True)

  def progressBarSetText(self, value):
    self.window.progressBar_createVideo.setFormat(value)

  def videoCreated(self):
    self.videoThread.quit()
    self.videoThread.wait()

  def updateResolution(self):
    resIndex = int(window.comboBox_resolution.currentIndex())
    res = self.resolutions[resIndex].split('x')
    self.settings.setValue('outputWidth',res[0])
    self.settings.setValue('outputHeight',res[1])
    self.drawPreview()

  def drawPreview(self):
    self.newTask.emit(self.selectedComponents)
    # self.processTask.emit()
    self.autosave()

  def showPreviewImage(self, image):
    self.previewWindow.changePixmap(image)

  def findComponents(self):
    def findComponents():
        srcPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'components')
        if os.path.exists(srcPath):
            for f in sorted(os.listdir(srcPath)):
                name, ext = os.path.splitext(f)
                if name.startswith("__"):
                    continue
                elif ext == '.py':
                    yield name
    return [import_module('components.%s' % name) for name in findComponents()]

  def addComponent(self, moduleIndex):
    index = len(self.pages)
    self.selectedComponents.append(self.modules[moduleIndex].Component())
    self.window.listWidget_componentList.addItem(self.selectedComponents[-1].__doc__)
    self.pages.append(self.selectedComponents[-1].widget(self))
    self.window.listWidget_componentList.setCurrentRow(index)
    self.window.stackedWidget.addWidget(self.pages[-1])
    self.window.stackedWidget.setCurrentIndex(index)
    self.selectedComponents[-1].update()
    self.updateOpenPresetComboBox(self.selectedComponents[-1])

  def insertComponent(self, moduleIndex):
    self.selectedComponents.insert(0, self.modules[moduleIndex].Component())
    self.window.listWidget_componentList.insertItem(0, self.selectedComponents[0].__doc__)
    self.pages.insert(0, self.selectedComponents[0].widget(self))
    self.window.listWidget_componentList.setCurrentRow(0)
    self.window.stackedWidget.insertWidget(0, self.pages[0])
    self.window.stackedWidget.setCurrentIndex(0)
    self.selectedComponents[0].update()
    self.updateOpenPresetComboBox(self.selectedComponents[0])

  def removeComponent(self):
    for selected in self.window.listWidget_componentList.selectedItems():
        index = self.window.listWidget_componentList.row(selected)
        self.window.stackedWidget.removeWidget(self.pages[index])
        self.window.listWidget_componentList.takeItem(index)
        self.selectedComponents.pop(index)
        self.pages.pop(index)
        self.changeComponentWidget()
    self.drawPreview()

  def changeComponentWidget(self):
    selected = self.window.listWidget_componentList.selectedItems()
    if selected:
        index = self.window.listWidget_componentList.row(selected[0])
        self.window.stackedWidget.setCurrentIndex(index)
        self.updateOpenPresetComboBox(self.selectedComponents[index])

  def moveComponentUp(self):
    row = self.window.listWidget_componentList.currentRow()
    if row > 0:
      module = self.selectedComponents[row]
      self.selectedComponents.pop(row)
      self.selectedComponents.insert(row - 1,module)
      page = self.pages[row]
      self.pages.pop(row)
      self.pages.insert(row - 1, page)
      item = self.window.listWidget_componentList.takeItem(row)
      self.window.listWidget_componentList.insertItem(row - 1, item)
      widget = self.window.stackedWidget.removeWidget(page)
      self.window.stackedWidget.insertWidget(row - 1, page)
      self.window.listWidget_componentList.setCurrentRow(row - 1)
      self.window.stackedWidget.setCurrentIndex(row -1)
      self.drawPreview()

  def moveComponentDown(self):
    row = self.window.listWidget_componentList.currentRow()
    if row < len(self.pages) + 1:
      module = self.selectedComponents[row]
      self.selectedComponents.pop(row)
      self.selectedComponents.insert(row + 1,module)
      page = self.pages[row]
      self.pages.pop(row)
      self.pages.insert(row + 1, page)
      item = self.window.listWidget_componentList.takeItem(row)
      self.window.listWidget_componentList.insertItem(row + 1, item)
      widget = self.window.stackedWidget.removeWidget(page)
      self.window.stackedWidget.insertWidget(row + 1, page)
      self.window.listWidget_componentList.setCurrentRow(row + 1)
      self.window.stackedWidget.setCurrentIndex(row + 1)
      self.drawPreview()

  def updateOpenPresetComboBox(self, component):
    self.window.comboBox_openPreset.clear()
    self.window.comboBox_openPreset.addItem("Component Presets")
    destination = os.path.join(self.presetDir,
        str(component).strip(), str(component.version()))
    if not os.path.exists(destination):
        os.makedirs(destination)
    for f in os.listdir(destination):
        self.window.comboBox_openPreset.addItem(f)

  def openSavePresetDialog(self):
    if self.window.listWidget_componentList.currentRow() == -1:
        return
    while True:
        newName, OK = QtGui.QInputDialog.getText(QtGui.QWidget(), 'Audio Visualizer', 'New Preset Name:')
        badName = False
        for letter in newName:
            if letter in string.punctuation:
                badName = True
        if badName:
            # some filesystems don't like bizarre characters
            self.showMessage("Preset names must contain only letters, numbers, and spaces.")
            continue
        if OK and newName:
            index = self.window.listWidget_componentList.currentRow()
            if index != -1:
                saveValueStore = self.selectedComponents[index].savePreset()
                componentName = str(self.selectedComponents[index]).strip()
                vers = self.selectedComponents[index].version()
                self.createPresetFile(componentName, vers, saveValueStore, newName)
        break

  def createPresetFile(self, componentName, version, saveValueStore, filename):
    dirname = os.path.join(self.presetDir, componentName, str(version))
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    filepath = os.path.join(dirname, filename)
    if os.path.exists(filepath):
        ch = self.showMessage("%s already exists! Overwrite it?" % filename, True, QtGui.QMessageBox.Warning)
        if not ch:
            return
        # remove old copies of the preset
        for i in range(0, self.window.comboBox_openPreset.count()):
            if self.window.comboBox_openPreset.itemText(i) == filename:
                self.window.comboBox_openPreset.removeItem(i)
    with open(filepath, 'w') as f:
        f.write(core.Core.stringOrderedDict(saveValueStore))
    self.window.comboBox_openPreset.addItem(filename)
    self.window.comboBox_openPreset.setCurrentIndex(self.window.comboBox_openPreset.count()-1)

  def openPreset(self):
    if self.window.comboBox_openPreset.currentIndex() < 1:
        return
    index = self.window.listWidget_componentList.currentRow()
    if index == -1:
        return
    filename = self.window.comboBox_openPreset.itemText(self.window.comboBox_openPreset.currentIndex())
    componentName = str(self.selectedComponents[index]).strip()
    version = self.selectedComponents[index].version()
    dirname = os.path.join(self.presetDir, componentName, str(version))
    filepath = os.path.join(dirname, filename)
    if not os.path.exists(filepath):
        self.window.comboBox_openPreset.removeItem(self.window.comboBox_openPreset.currentIndex())
        return
    with open(filepath, 'r') as f:
        for line in f:
            saveValueStore = dict(eval(line.strip()))
            break
    self.selectedComponents[index].loadPreset(saveValueStore)
    self.drawPreview()

  def saveCurrentProject(self):
    if self.currentProject:
        self.createProjectFile(self.currentProject)
    else:
        self.openSaveProjectDialog()

  def openSaveProjectDialog(self):
    filename = QtGui.QFileDialog.getSaveFileName(self.window,
        "Create Project File", self.settings.value("projectDir"),
        "Project Files (*.avp)")
    if not filename:
        return
    self.createProjectFile(filename)
    
  def createProjectFile(self, filepath):
    if not filepath.endswith(".avp"):
        filepath += '.avp'
    with open(filepath, 'w') as f:
        print('creating %s' % filepath)
        f.write('[Components]\n')
        for comp in self.selectedComponents:
            saveValueStore = comp.savePreset()
            f.write('%s\n' % str(comp))
            f.write('%s\n' % str(comp.version()))
            f.write('%s\n' % core.Core.stringOrderedDict(saveValueStore))
    if filepath != self.autosavePath:
        self.settings.setValue("projectDir", os.path.dirname(filepath))
        self.settings.setValue("currentProject", filepath)
        self.currentProject = filepath
            
  def openOpenProjectDialog(self):
    filename = QtGui.QFileDialog.getOpenFileName(self.window,
        "Open Project File", self.settings.value("projectDir"),
        "Project Files (*.avp)")
    self.openProject(filename)
    
  def openProject(self, filepath):
    if not filepath or not os.path.exists(filepath) or not filepath.endswith('.avp'):
        return
    self.clear()
    self.currentProject = filepath
    self.settings.setValue("currentProject", filepath)
    self.settings.setValue("projectDir", os.path.dirname(filepath))
    compNames = [mod.Component.__doc__ for mod in self.modules]
    try:
        with open(filepath, 'r') as f:
            validSections = ('Components')
            section = ''
            def parseLine(line):
                line = line.strip()
                newSection = ''
                if line.startswith('[') and line.endswith(']') and line[1:-1] in validSections:
                    newSection = line[1:-1]
                return line, newSection
                
            i = 0
            for line in f:
                line, newSection = parseLine(line)
                if newSection:
                    section = str(newSection)
                    continue
                if line and section == 'Components':
                    if i == 0:
                        compIndex = compNames.index(line)
                        self.addComponent(compIndex)
                        i += 1
                    elif i == 1:
                        # version, not used yet
                        i += 1
                    elif i == 2:
                        saveValueStore = dict(eval(line))
                        self.selectedComponents[-1].loadPreset(saveValueStore)
                        i = 0
    except (IndexError, ValueError, KeyError, NameError, SyntaxError, AttributeError, TypeError) as e:
        self.clear()
        typ, value, _ = sys.exc_info()
        msg = '%s: %s' % (typ.__name__, value)
        self.showMessage("Project file '%s' is corrupted." % filepath, False,
            QtGui.QMessageBox.Warning, msg)

  def showMessage(self, string, showCancel=False, icon=QtGui.QMessageBox.Information, detail=None):
    msg = QtGui.QMessageBox()
    msg.setIcon(icon)
    msg.setText(string)
    msg.setDetailedText(detail)
    if showCancel:
        msg.setStandardButtons(QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel)
    else:
        msg.setStandardButtons(QtGui.QMessageBox.Ok)
    ch = msg.exec_()
    if ch == 1024:
        return True
    return False
    
  def clear(self):
    ''' empty out all components and fields, get a blank slate '''
    self.selectedComponents = []
    self.window.listWidget_componentList.clear()
    for widget in self.pages:
        self.window.stackedWidget.removeWidget(widget)
    self.pages = []

def LoadDefaultSettings(self):
  self.resolutions = [
      '1920x1080',
      '1280x720',
      '854x480'
    ]

  default = {
    "outputWidth": 1280,
    "outputHeight": 720,
    "outputFrameRate": 30,
    "outputAudioCodec": "aac",
    "outputAudioBitrate": "192k",
    "outputVideoCodec": "libx264",
    "outputVideoFormat": "yuv420p",
    "outputPreset": "medium",
    "outputFormat": "mp4",
    "projectDir" : os.path.join(self.dataDir, 'projects'),
  }
  
  for parm, value in default.items():
    if self.settings.value(parm) == None:
      self.settings.setValue(parm,value)


''' ####### commandline functionality broken until we decide how to implement it
if len(sys.argv) > 1:
  # command line mode
  app = QtGui.QApplication(sys.argv, False)
  command = Command()
  signal.signal(signal.SIGINT, command.cleanUp)
  sys.exit(app.exec_())
else:
'''
# gui mode
if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    app.setApplicationName("audio-visualizer")
    app.setOrganizationName("audio-visualizer")
    window = uic.loadUi(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mainwindow.ui"))
    # window.adjustSize()
    desc = QtGui.QDesktopWidget()
    dpi = desc.physicalDpiX()
    
    topMargin = 0 if (dpi == 96) else int(10 * (dpi / 96))
    window.resize(window.width() * (dpi / 96), window.height() * (dpi / 96))
    #window.verticalLayout_2.setContentsMargins(0, topMargin, 0, 0)
  
    main = Main(window)

    signal.signal(signal.SIGINT, main.cleanUp)
    atexit.register(main.cleanUp)

    sys.exit(app.exec_())
