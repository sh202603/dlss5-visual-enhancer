import QtQuick
import ".."
import "../controls"
import "../components"

Item {
    id: root

    property var appBridge: null
    readonly property int adaptiveInspectorWidth: width >= 2560 ? 520 : (width >= 1920 ? 460 : (width >= 1600 ? 420 : (width >= 1280 ? 380 : 340)))

    Row {
        anchors.fill: parent

        // Center Area: Media Viewport + Batch Queue Drawer
        Item {
            width: parent.width - sidebar.width
            height: parent.height

            MediaViewport {
                id: viewport
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: queueDrawer.top
                appBridge: root.appBridge
            }

            BatchQueueDrawer {
                id: queueDrawer
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                appBridge: root.appBridge
                queueModel: root.appBridge ? root.appBridge.fiQueue : null
                hidden: appBridge ? appBridge.focusPreview : false
                expandedHeight: appBridge ? appBridge.queueHeight : 190
            }
        }

        // Right Sidebar
        Rectangle {
            id: sidebar
            width: appBridge && appBridge.focusPreview ? 0 : Math.max(root.adaptiveInspectorWidth, Math.min(560, appBridge ? appBridge.inspectorWidth : root.adaptiveInspectorWidth))
            height: parent.height
            visible: width > 0
            color: Theme.bgSurface
            border.color: Theme.borderSubtle
            border.width: 1

            MouseArea {
                id: inspectorResizeHandle
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 6
                z: 100
                cursorShape: Qt.SizeHorCursor
                onPositionChanged: (mouse) => {
                    if (!pressed || !appBridge) return
                    var pt = inspectorResizeHandle.mapToItem(root, mouse.x, mouse.y)
                    appBridge.inspectorWidth = Math.max(300, Math.min(560, root.width - pt.x))
                }
            }

            Column {
                anchors.fill: parent

                Flickable {
                    width: parent.width
                    height: parent.height - actionBar.height
                    contentWidth: width
                    contentHeight: contentCol.implicitHeight + 24
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: contentCol
                        width: parent.width - 24
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: parent.top
                        anchors.topMargin: 12
                        spacing: 12

                        // Card 1: Frame Generation Configuration
                        AppCard {
                            width: parent.width
                            title: "DLSS-G Frame Generation"

                            Column {
                                width: parent.width
                                spacing: 12

                                AppComboBox {
                                    width: parent.width
                                    label: "Target Output Frame Rate"
                                    model: appBridge ? appBridge.fiFpsChoices : []
                                    currentValue: appBridge ? appBridge.fiTargetFps : "60"
                                    onActivated: (v) => { if (appBridge) appBridge.fiTargetFps = v }
                                }

                                AppSegmentedControl {
                                    width: parent.width
                                    label: "DLSS-G Engine"
                                    model: appBridge ? appBridge.fiEngineChoices : []
                                    currentValue: appBridge ? appBridge.fiEngine : "Auto"
                                    onActivated: (v) => { if (appBridge) appBridge.fiEngine = v }
                                }

                                Text {
                                    width: parent.width
                                    text: appBridge ? appBridge.outputEstimate : ""
                                    wrapMode: Text.Wrap
                                    font.family: Theme.monoFontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                    color: Theme.textMuted
                                }
                            }
                        }

                        // Card 2: Export Settings
                        AppCard {
                            width: parent.width
                            title: "Encoding & Output"

                            Column {
                                width: parent.width
                                spacing: 12

                                AppComboBox {
                                    width: parent.width
                                    label: "Video Codec"
                                    model: appBridge ? appBridge.codecChoices : []
                                    currentValue: appBridge ? appBridge.fiCodec : "H.264 (NVIDIA NVENC)"
                                    onActivated: (v) => { if (appBridge) appBridge.fiCodec = v }
                                }

                                AppComboBox {
                                    width: parent.width
                                    label: "Container (automatic)"
                                    model: appBridge ? appBridge.containerChoices : []
                                    currentValue: appBridge ? appBridge.fiContainer : "MP4"
                                    enabled: false
                                }

                                AppComboBox {
                                    width: parent.width
                                    label: "Quality Preset"
                                    model: appBridge ? appBridge.encodingQualityChoices : []
                                    currentValue: appBridge ? appBridge.fiQuality : "Auto (Default)"
                                    onActivated: (v) => { if (appBridge) appBridge.fiQuality = v }
                                }

                                AppCheckBox {
                                    label: "Preserve 10-bit HDR"
                                    checked: appBridge ? appBridge.fiHdrMode : false
                                    enabled: appBridge ? appBridge.fiHdrSupported : false
                                    onToggled: (c) => { if (appBridge) appBridge.fiHdrMode = c }
                                }

                                AppSegmentedControl {
                                    width: parent.width
                                    label: "Rename Mode"
                                    model: appBridge ? appBridge.renameModeChoices : []
                                    currentValue: appBridge ? appBridge.fiRenameMode : "Auto"
                                    onActivated: (v) => { if (appBridge) appBridge.fiRenameMode = v }
                                }

                                AppTextField {
                                    visible: appBridge && appBridge.fiRenameMode === "Custom"
                                    width: parent.width
                                    label: "Custom Suffix"
                                    text: appBridge ? appBridge.fiCustomSuffix : "_Frame_Interpolation"
                                    onTextEdited: (t) => { if (appBridge) appBridge.fiCustomSuffix = t }
                                }
                            }
                        }
                    }
                }

                // Sticky Bottom Action Bar
                Rectangle {
                    id: actionBar
                    width: parent.width
                    height: 54
                    color: Theme.bgSurface
                    border.color: Theme.borderSubtle
                    border.width: 1

                    Column {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        Row {
                            width: parent.width
                            spacing: 8

                            AppButton {
                                text: "Preview"
                                width: 90
                                buttonHeight: 34
                                enabled: appBridge ? appBridge.canPreview : false
                                onClicked: { if (appBridge) appBridge.renderPreviewAt(viewport.playheadMs) }
                            }

                            AppComboBox {
                                width: 60
                                comboHeight: 34
                                dropUp: true
                                model: appBridge ? appBridge.fiPreviewLengthChoices : []
                                currentValue: appBridge ? appBridge.fiPreviewLength : "3"
                                onActivated: (v) => { if (appBridge) appBridge.fiPreviewLength = v }
                            }

                            AppButton {
                                text: appBridge && appBridge.canStop ? "Stop" : "Interpolate Video(s)"
                                variant: appBridge && appBridge.canStop ? "danger" : "primary"
                                width: parent.width - 362
                                buttonHeight: 34
                                enabled: appBridge ? (appBridge.canStop || appBridge.canRender) : false
                                onClicked: {
                                    if (appBridge) {
                                        if (appBridge.canStop) appBridge.stopActiveBatch()
                                        else if (appBridge.canRender) appBridge.startActiveBatch()
                                    }
                                }
                            }

                            AppButton {
                                text: "Reset"
                                width: 90
                                buttonHeight: 34
                                onClicked: { if (appBridge) appBridge.resetTabSettings("frame-interpolation") }
                            }

                            AppButton {
                                text: "Outputs"
                                width: 90
                                buttonHeight: 34
                                onClicked: { if (appBridge) appBridge.openFolder("") }
                            }
                        }
                    }
                }
            }
        }
    }
}
