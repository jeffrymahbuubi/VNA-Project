# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.10.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLayout, QLineEdit,
    QMainWindow, QMenu, QMenuBar, QPushButton,
    QRadioButton, QSizePolicy, QStatusBar, QVBoxLayout,
    QWidget)
import resources_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1280, 720)
        MainWindow.setMinimumSize(QSize(1280, 720))
        MainWindow.setMaximumSize(QSize(1920, 1080))
        font = QFont()
        font.setFamilies([u"Times New Roman"])
        font.setPointSize(12)
        MainWindow.setFont(font)
        self.actionLoad = QAction(MainWindow)
        self.actionLoad.setObjectName(u"actionLoad")
        self.actionLoad_yaml_config = QAction(MainWindow)
        self.actionLoad_yaml_config.setObjectName(u"actionLoad_yaml_config")
        self.actionSerial_LibreVNA_USB = QAction(MainWindow)
        self.actionSerial_LibreVNA_USB.setObjectName(u"actionSerial_LibreVNA_USB")
        font1 = QFont()
        font1.setFamilies([u"Times New Roman"])
        self.actionSerial_LibreVNA_USB.setFont(font1)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setMinimumSize(QSize(0, 0))
        self.centralwidget.setMaximumSize(QSize(1920, 1080))
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(-1, 0, -1, 0)
        self.mainWidget = QWidget(self.centralwidget)
        self.mainWidget.setObjectName(u"mainWidget")
        self.mainWidget.setMaximumSize(QSize(1920, 200))
        self.horizontalLayout_3 = QHBoxLayout(self.mainWidget)
        self.horizontalLayout_3.setSpacing(0)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(9, 0, -1, 0)
        self.logoWTMH = QLabel(self.mainWidget)
        self.logoWTMH.setObjectName(u"logoWTMH")
        self.logoWTMH.setMinimumSize(QSize(120, 120))
        self.logoWTMH.setMaximumSize(QSize(120, 120))
        self.logoWTMH.setTextFormat(Qt.TextFormat.PlainText)
        self.logoWTMH.setPixmap(QPixmap(u":/ui/WTMH.png"))
        self.logoWTMH.setScaledContents(True)

        self.horizontalLayout_3.addWidget(self.logoWTMH)

        self.configurationWidget = QWidget(self.mainWidget)
        self.configurationWidget.setObjectName(u"configurationWidget")
        self.configurationWidget.setEnabled(True)
        self.configurationWidget.setMaximumSize(QSize(16777215, 190))
        self.horizontalLayout_4 = QHBoxLayout(self.configurationWidget)
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.widget = QWidget(self.configurationWidget)
        self.widget.setObjectName(u"widget")
        self.widget.setMaximumSize(QSize(700, 16777215))
        self.verticalLayout_4 = QVBoxLayout(self.widget)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.sweepBox = QGroupBox(self.widget)
        self.sweepBox.setObjectName(u"sweepBox")
        self.sweepBox.setMinimumSize(QSize(0, 0))
        font2 = QFont()
        font2.setFamilies([u"Times New Roman"])
        font2.setPointSize(12)
        font2.setBold(True)
        self.sweepBox.setFont(font2)
        self.sweepBox.setAutoFillBackground(False)
        self.sweepBox.setFlat(False)
        self.horizontalLayout = QHBoxLayout(self.sweepBox)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.startFrequencyLabel = QLabel(self.sweepBox)
        self.startFrequencyLabel.setObjectName(u"startFrequencyLabel")
        font3 = QFont()
        font3.setFamilies([u"Times New Roman"])
        font3.setPointSize(12)
        font3.setBold(False)
        self.startFrequencyLabel.setFont(font3)

        self.horizontalLayout.addWidget(self.startFrequencyLabel)

        self.startFrequencyLineEdit = QLineEdit(self.sweepBox)
        self.startFrequencyLineEdit.setObjectName(u"startFrequencyLineEdit")

        self.horizontalLayout.addWidget(self.startFrequencyLineEdit)

        self.centerFrequencyLabel = QLabel(self.sweepBox)
        self.centerFrequencyLabel.setObjectName(u"centerFrequencyLabel")
        self.centerFrequencyLabel.setFont(font3)

        self.horizontalLayout.addWidget(self.centerFrequencyLabel)

        self.centerFrequencyLineEdit = QLineEdit(self.sweepBox)
        self.centerFrequencyLineEdit.setObjectName(u"centerFrequencyLineEdit")
        self.centerFrequencyLineEdit.setAutoFillBackground(True)

        self.horizontalLayout.addWidget(self.centerFrequencyLineEdit)

        self.stopFrequencyLabel = QLabel(self.sweepBox)
        self.stopFrequencyLabel.setObjectName(u"stopFrequencyLabel")
        self.stopFrequencyLabel.setFont(font3)

        self.horizontalLayout.addWidget(self.stopFrequencyLabel)

        self.stopFrequencyLineEdit = QLineEdit(self.sweepBox)
        self.stopFrequencyLineEdit.setObjectName(u"stopFrequencyLineEdit")
        self.stopFrequencyLineEdit.setAutoFillBackground(True)

        self.horizontalLayout.addWidget(self.stopFrequencyLineEdit)

        self.spanFrequencyLabel = QLabel(self.sweepBox)
        self.spanFrequencyLabel.setObjectName(u"spanFrequencyLabel")
        self.spanFrequencyLabel.setFont(font3)

        self.horizontalLayout.addWidget(self.spanFrequencyLabel)

        self.spanFrequencyLineEdit = QLineEdit(self.sweepBox)
        self.spanFrequencyLineEdit.setObjectName(u"spanFrequencyLineEdit")
        self.spanFrequencyLineEdit.setAutoFillBackground(True)

        self.horizontalLayout.addWidget(self.spanFrequencyLineEdit)

        self.numberOfSweepLabel = QLabel(self.sweepBox)
        self.numberOfSweepLabel.setObjectName(u"numberOfSweepLabel")
        self.numberOfSweepLabel.setFont(font3)

        self.horizontalLayout.addWidget(self.numberOfSweepLabel)

        self.numberOfSweepLineEdit = QLineEdit(self.sweepBox)
        self.numberOfSweepLineEdit.setObjectName(u"numberOfSweepLineEdit")
        self.numberOfSweepLineEdit.setAutoFillBackground(True)

        self.horizontalLayout.addWidget(self.numberOfSweepLineEdit)


        self.verticalLayout_4.addWidget(self.sweepBox)

        self.acqusitionsBox = QGroupBox(self.widget)
        self.acqusitionsBox.setObjectName(u"acqusitionsBox")
        self.acqusitionsBox.setMinimumSize(QSize(0, 0))
        self.acqusitionsBox.setFont(font2)
        self.horizontalLayout_2 = QHBoxLayout(self.acqusitionsBox)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.levelLabel = QLabel(self.acqusitionsBox)
        self.levelLabel.setObjectName(u"levelLabel")
        self.levelLabel.setFont(font3)

        self.horizontalLayout_2.addWidget(self.levelLabel)

        self.levelLineEdit = QLineEdit(self.acqusitionsBox)
        self.levelLineEdit.setObjectName(u"levelLineEdit")
        self.levelLineEdit.setAutoFillBackground(True)

        self.horizontalLayout_2.addWidget(self.levelLineEdit)

        self.pointsLabel = QLabel(self.acqusitionsBox)
        self.pointsLabel.setObjectName(u"pointsLabel")
        self.pointsLabel.setFont(font3)

        self.horizontalLayout_2.addWidget(self.pointsLabel)

        self.pointsLineEdit = QLineEdit(self.acqusitionsBox)
        self.pointsLineEdit.setObjectName(u"pointsLineEdit")
        self.pointsLineEdit.setAutoFillBackground(True)

        self.horizontalLayout_2.addWidget(self.pointsLineEdit)

        self.ifbwFrequencyLabel = QLabel(self.acqusitionsBox)
        self.ifbwFrequencyLabel.setObjectName(u"ifbwFrequencyLabel")
        self.ifbwFrequencyLabel.setFont(font3)

        self.horizontalLayout_2.addWidget(self.ifbwFrequencyLabel)

        self.ifbwFrequencyLineEdit = QLineEdit(self.acqusitionsBox)
        self.ifbwFrequencyLineEdit.setObjectName(u"ifbwFrequencyLineEdit")
        self.ifbwFrequencyLineEdit.setAutoFillBackground(True)

        self.horizontalLayout_2.addWidget(self.ifbwFrequencyLineEdit)


        self.verticalLayout_4.addWidget(self.acqusitionsBox)


        self.horizontalLayout_4.addWidget(self.widget)

        self.modeConfigurationBox = QGroupBox(self.configurationWidget)
        self.modeConfigurationBox.setObjectName(u"modeConfigurationBox")
        self.modeConfigurationBox.setMinimumSize(QSize(0, 150))
        self.modeConfigurationBox.setMaximumSize(QSize(16777215, 16777215))
        self.modeConfigurationBox.setFont(font2)
        self.verticalLayout_3 = QVBoxLayout(self.modeConfigurationBox)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.modeSelectionWidget = QWidget(self.modeConfigurationBox)
        self.modeSelectionWidget.setObjectName(u"modeSelectionWidget")
        self.modeSelectionWidget.setMinimumSize(QSize(0, 50))
        self.modeSelectionWidget.setMaximumSize(QSize(1000, 1000))
        self.modeSelectionWidget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.modeSelectionWidget.setAutoFillBackground(False)
        self.horizontalLayout_5 = QHBoxLayout(self.modeSelectionWidget)
        self.horizontalLayout_5.setSpacing(0)
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.horizontalLayout_5.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        self.horizontalLayout_5.setContentsMargins(9, 0, 9, 0)
        self.modeSelectionLabel = QLabel(self.modeSelectionWidget)
        self.modeSelectionLabel.setObjectName(u"modeSelectionLabel")
        self.modeSelectionLabel.setFont(font3)

        self.horizontalLayout_5.addWidget(self.modeSelectionLabel)

        self.radioButtonWidget = QWidget(self.modeSelectionWidget)
        self.radioButtonWidget.setObjectName(u"radioButtonWidget")
        self.verticalLayout_5 = QVBoxLayout(self.radioButtonWidget)
        self.verticalLayout_5.setSpacing(0)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalLayout_5.setContentsMargins(-1, 0, 0, 0)
        self.deviceSanityCheck = QRadioButton(self.radioButtonWidget)
        self.deviceSanityCheck.setObjectName(u"deviceSanityCheck")
        font4 = QFont()
        font4.setFamilies([u"Times New Roman"])
        font4.setPointSize(10)
        font4.setBold(False)
        self.deviceSanityCheck.setFont(font4)

        self.verticalLayout_5.addWidget(self.deviceSanityCheck)

        self.continuousMonitoring = QRadioButton(self.radioButtonWidget)
        self.continuousMonitoring.setObjectName(u"continuousMonitoring")
        self.continuousMonitoring.setFont(font4)

        self.verticalLayout_5.addWidget(self.continuousMonitoring)


        self.horizontalLayout_5.addWidget(self.radioButtonWidget)


        self.verticalLayout_3.addWidget(self.modeSelectionWidget)

        self.userInputDurationTimeWidget = QWidget(self.modeConfigurationBox)
        self.userInputDurationTimeWidget.setObjectName(u"userInputDurationTimeWidget")
        self.gridLayout = QGridLayout(self.userInputDurationTimeWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setHorizontalSpacing(10)
        self.gridLayout.setVerticalSpacing(2)
        self.gridLayout.setContentsMargins(12, 0, 9, 7)
        self.monitorDurationsLabel = QLabel(self.userInputDurationTimeWidget)
        self.monitorDurationsLabel.setObjectName(u"monitorDurationsLabel")
        self.monitorDurationsLabel.setFont(font3)

        self.gridLayout.addWidget(self.monitorDurationsLabel, 0, 0, 1, 1)

        self.monitorDurationcomboBox = QComboBox(self.userInputDurationTimeWidget)
        self.monitorDurationcomboBox.setObjectName(u"monitorDurationcomboBox")

        self.gridLayout.addWidget(self.monitorDurationcomboBox, 0, 1, 1, 1)

        self.logIntervalLabel = QLabel(self.userInputDurationTimeWidget)
        self.logIntervalLabel.setObjectName(u"logIntervalLabel")
        self.logIntervalLabel.setFont(font3)

        self.gridLayout.addWidget(self.logIntervalLabel, 1, 0, 1, 1)

        self.logIntervallineEdit = QLineEdit(self.userInputDurationTimeWidget)
        self.logIntervallineEdit.setObjectName(u"logIntervallineEdit")

        self.gridLayout.addWidget(self.logIntervallineEdit, 1, 1, 1, 1)


        self.verticalLayout_3.addWidget(self.userInputDurationTimeWidget)


        self.horizontalLayout_4.addWidget(self.modeConfigurationBox)


        self.horizontalLayout_3.addWidget(self.configurationWidget)

        self.pushButton = QPushButton(self.mainWidget)
        self.pushButton.setObjectName(u"pushButton")
        self.pushButton.setMinimumSize(QSize(200, 145))
        font5 = QFont()
        font5.setFamilies([u"Segoe UI"])
        font5.setPointSize(24)
        font5.setBold(True)
        self.pushButton.setFont(font5)
        self.pushButton.setStyleSheet(u"QPushButton{\n"
"	    background-color: rgb(74, 222, 128);\n"
"        border-style: solid;\n"
"        border-width: 2px;\n"
"        border-radius: 10px;  \n"
"        border-color: rgb(74, 222, 128);\n"
"}\n"
"\n"
"QPushButton:hover {\n"
"        border-color: #38bdf8;  /* Change border color on hover */\n"
"}")

        self.horizontalLayout_3.addWidget(self.pushButton)


        self.verticalLayout.addWidget(self.mainWidget)

        self.tracesBox = QGroupBox(self.centralwidget)
        self.tracesBox.setObjectName(u"tracesBox")
        self.tracesBox.setFont(font2)
        self.verticalLayout_2 = QVBoxLayout(self.tracesBox)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(-1, 0, -1, -1)
        self.s11TracePlot = QLabel(self.tracesBox)
        self.s11TracePlot.setObjectName(u"s11TracePlot")
        font6 = QFont()
        font6.setFamilies([u"Times New Roman"])
        font6.setPointSize(1)
        font6.setBold(True)
        self.s11TracePlot.setFont(font6)
        self.s11TracePlot.setPixmap(QPixmap(u":/ui/placeholder-s11.png"))
        self.s11TracePlot.setScaledContents(True)

        self.verticalLayout_2.addWidget(self.s11TracePlot)


        self.verticalLayout.addWidget(self.tracesBox)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1280, 33))
        self.menuDevice = QMenu(self.menubar)
        self.menuDevice.setObjectName(u"menuDevice")
        self.menuDevice.setFont(font)
        self.menuConnect_to = QMenu(self.menuDevice)
        self.menuConnect_to.setObjectName(u"menuConnect_to")
        self.menuConnect_to.setFont(font)
        self.menuCalibration = QMenu(self.menubar)
        self.menuCalibration.setObjectName(u"menuCalibration")
        self.menuCalibration.setFont(font)
        self.menuConfiguration = QMenu(self.menubar)
        self.menuConfiguration.setObjectName(u"menuConfiguration")
        self.menuConfiguration.setFont(font)
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuDevice.menuAction())
        self.menubar.addAction(self.menuCalibration.menuAction())
        self.menubar.addAction(self.menuConfiguration.menuAction())
        self.menuDevice.addAction(self.menuConnect_to.menuAction())
        self.menuConnect_to.addAction(self.actionSerial_LibreVNA_USB)
        self.menuCalibration.addAction(self.actionLoad)
        self.menuConfiguration.addAction(self.actionLoad_yaml_config)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.actionLoad.setText(QCoreApplication.translate("MainWindow", u"Load .cal file", None))
        self.actionLoad_yaml_config.setText(QCoreApplication.translate("MainWindow", u"Load .yaml config", None))
        self.actionSerial_LibreVNA_USB.setText(QCoreApplication.translate("MainWindow", u"Serial (LibreVNA/USB)", None))
        self.logoWTMH.setText("")
        self.sweepBox.setTitle(QCoreApplication.translate("MainWindow", u"Sweep Configuration", None))
        self.startFrequencyLabel.setText(QCoreApplication.translate("MainWindow", u"Start", None))
        self.centerFrequencyLabel.setText(QCoreApplication.translate("MainWindow", u"Center", None))
        self.stopFrequencyLabel.setText(QCoreApplication.translate("MainWindow", u"Stop", None))
        self.spanFrequencyLabel.setText(QCoreApplication.translate("MainWindow", u"Span", None))
        self.numberOfSweepLabel.setText(QCoreApplication.translate("MainWindow", u"No. of Sweep", None))
        self.acqusitionsBox.setTitle(QCoreApplication.translate("MainWindow", u"Acqusition Configuration", None))
        self.levelLabel.setText(QCoreApplication.translate("MainWindow", u"Level", None))
        self.pointsLabel.setText(QCoreApplication.translate("MainWindow", u"Points", None))
        self.ifbwFrequencyLabel.setText(QCoreApplication.translate("MainWindow", u"IF BW:", None))
        self.modeConfigurationBox.setTitle(QCoreApplication.translate("MainWindow", u"Mode Configuration", None))
        self.modeSelectionLabel.setText(QCoreApplication.translate("MainWindow", u"Mode Selection", None))
        self.deviceSanityCheck.setText(QCoreApplication.translate("MainWindow", u"Device Sanity Check", None))
        self.continuousMonitoring.setText(QCoreApplication.translate("MainWindow", u"Continuous Monitoring", None))
        self.monitorDurationsLabel.setText(QCoreApplication.translate("MainWindow", u"Monitor Durations (s)", None))
        self.logIntervalLabel.setText(QCoreApplication.translate("MainWindow", u"Log Interval (ms)", None))
        self.pushButton.setText(QCoreApplication.translate("MainWindow", u"Collect Data", None))
        self.tracesBox.setTitle(QCoreApplication.translate("MainWindow", u"Traces", None))
        self.s11TracePlot.setText("")
        self.menuDevice.setTitle(QCoreApplication.translate("MainWindow", u"Device", None))
        self.menuConnect_to.setTitle(QCoreApplication.translate("MainWindow", u"Connect to", None))
        self.menuCalibration.setTitle(QCoreApplication.translate("MainWindow", u"Calibration", None))
        self.menuConfiguration.setTitle(QCoreApplication.translate("MainWindow", u"Configuration", None))
    # retranslateUi

