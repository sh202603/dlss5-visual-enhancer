import QtQuick
import ".."
import "../controls"
import "../components"

Item {
    id: root

    property var appBridge: null
    readonly property int adaptiveInspectorWidth: width >= 2560 ? 520 : (width >= 1920 ? 460 : (width >= 1600 ? 420 : (width >= 1280 ? 380 : 340)))

    readonly property bool isImage: appBridge ? (appBridge.nrMode === "Image") : true
    readonly property var activeQueue: appBridge ? (isImage ? appBridge.nrImageQueue : appBridge.nrVideoQueue) : null

    Row {
        anchors.fill: parent

        // Main Center Area: Media Viewport + Batch Queue Drawer
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
                queueModel: root.activeQueue
                hidden: appBridge ? appBridge.focusPreview : false
                expandedHeight: appBridge ? appBridge.queueHeight : 190
            }
        }

        // Right Sidebar: Parameters & Inspector (Topaz-style)
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

                // Workflow Submode Switcher: Image vs Video
                Rectangle {
                    width: parent.width
                    height: 48
                    color: Theme.bgSurface
                    border.color: Theme.borderSubtle
                    border.width: 1

                    Row {
                        anchors.centerIn: parent
                        spacing: 8

                        AppSegmentedControl {
                            model: ["Image", "Video"]
                            currentValue: root.appBridge ? root.appBridge.nrMode : "Image"
                            onActivated: (val) => {
                                if (root.appBridge) root.appBridge.nrMode = val
                            }
                        }
                    }
                }

                // Scrollable Cards Area
                Flickable {
                    id: flick
                    width: parent.width
                    height: parent.height - 48 - actionBar.height
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

                        // Card 1: Neural Rendering Parameters
                        AppCard {
                            width: parent.width
                            title: "DLSS Neural Model"

                            Column {
                                width: parent.width
                                spacing: 12

                                AppSegmentedControl {
                                    width: parent.width
                                    label: "NR Style"
                                    model: appBridge ? appBridge.nrStyleChoices : []
                                    currentValue: appBridge ? appBridge.nrStyle : "Default"
                                    onActivated: (v) => { if (appBridge) appBridge.nrStyle = v }
                                }

                                AppComboBox {
                                    width: parent.width
                                    label: "Scale"
model: appBridge ? appBridge.nrScaleChoices : []
                                    currentValue: appBridge ? appBridge.upscalingFactor : 1.0
                                    onActivated: (v) => { if (appBridge) appBridge.upscalingFactor = v }
                                }

                                AppSlider {
                                    width: parent.width
                                    label: "NR Intensity"
                                    from: 0.0
                                    to: 2.0
                                    stepSize: 0.05
                                    defaultValue: 1.0
                                    value: appBridge ? appBridge.nrIntensity : 1.0
                                    onValueModified: (v) => { if (appBridge) appBridge.nrIntensity = v }
                                }

                                AppSlider {
                                    width: parent.width
                                    label: "NR Passes"
                                    from: 1
                                    to: 4
                                    stepSize: 1
                                    precision: 0
                                    defaultValue: 1
                                    value: appBridge ? appBridge.nrPasses : 1
                                    onValueModified: (v) => { if (appBridge) appBridge.nrPasses = Math.round(v) }
                                }

                                AppSlider {
                                    width: parent.width
                                    label: "Local Tone Strength"
                                    from: 0.0
                                    to: 2.0
                                    stepSize: 0.05
                                    defaultValue: 1.0
                                    value: appBridge ? appBridge.localToneStrength : 1.0
                                    onValueModified: (v) => { if (appBridge) appBridge.localToneStrength = v }
                                }

                                AppSlider {
                                    width: parent.width
                                    label: "Local Structure Strength"
                                    from: 0.0
                                    to: 2.0
                                    stepSize: 0.05
                                    defaultValue: 1.0
                                    value: appBridge ? appBridge.localStructureStrength : 1.0
                                    onValueModified: (v) => { if (appBridge) appBridge.localStructureStrength = v }
                                }

                                AppSlider {
                                    width: parent.width
                                    label: "Skin Structure Strength"
                                    from: -1.0
                                    to: 2.0
                                    stepSize: 0.05
                                    defaultValue: -1.0
                                    value: appBridge ? appBridge.skinStructureStrength : -1.0
                                    onValueModified: (v) => { if (appBridge) appBridge.skinStructureStrength = v }
                                }

                                AppSwitch {
                                    label: "Automatic Mask"
                                    checked: appBridge ? appBridge.automaticMask : false
                                    onToggled: (c) => { if (appBridge) appBridge.automaticMask = c }
                                }

                                AppSlider {
                                    visible: !root.isImage
                                    width: parent.width
                                    label: "Shimmer Suppression"
                                    from: 0.0
                                    to: 1.0
                                    stepSize: 0.05
                                    defaultValue: 0.70
                                    value: appBridge ? appBridge.shimmerSuppression : 0.70
                                    onValueModified: (v) => { if (appBridge) appBridge.shimmerSuppression = v }
                                }
                            }
                        }

                        // Card 2: Composition & Masking
                        CompositionCard {
                            width: parent.width
                            appBridge: root.appBridge
                        }

                        // Card 3: Export & Encoding Settings
                        AppCard {
                            width: parent.width
                            title: "Export Settings"

                            Column {
                                width: parent.width
                                spacing: 12

                                // IMAGE SPECIFIC
                                Column {
                                    visible: root.isImage
                                    width: parent.width
                                    spacing: 12

                                    AppComboBox {
                                        width: parent.width
                                        label: "Output Format"
                                        model: appBridge ? appBridge.imageFormatChoices : []
                                        currentValue: appBridge ? appBridge.imageFormat : "PNG"
                                        onActivated: (v) => { if (appBridge) appBridge.imageFormat = v }
                                    }

                                    AppSlider {
                                        width: parent.width
                                        label: "Image Quality"
                                        from: 1
                                        to: 100
                                        stepSize: 1
                                        precision: 0
                                        defaultValue: 95
                                        value: appBridge ? appBridge.imageQuality : 95
                                        onValueModified: (v) => { if (appBridge) appBridge.imageQuality = Math.round(v) }
                                    }

                                }

                                // VIDEO SPECIFIC
                                Column {
                                    visible: !root.isImage
                                    width: parent.width
                                    spacing: 12

                                    AppComboBox {
                                        width: parent.width
                                        label: "Video Codec"
                                        model: appBridge ? appBridge.codecChoices : []
                                        currentValue: appBridge ? appBridge.videoCodec : "H.264 (NVIDIA NVENC)"
                                        onActivated: (v) => { if (appBridge) appBridge.videoCodec = v }
                                    }

                                    AppComboBox {
                                        width: parent.width
                                        label: "Container"
                                        model: appBridge ? appBridge.containerChoices : []
                                        currentValue: appBridge ? appBridge.videoContainer : "MP4"
                                        enabled: false
                                    }

                                    AppComboBox {
                                        width: parent.width
                                        label: "Encoding Quality"
                                        visible: !appBridge || appBridge.fixedQualityCodecs.indexOf(appBridge.videoCodec) < 0
                                        model: appBridge ? appBridge.encodingQualityChoices : []
                                        currentValue: appBridge ? appBridge.videoQuality : "Auto (Default)"
                                        onActivated: (v) => { if (appBridge) appBridge.videoQuality = v }
                                    }

                                    Text {
                                        visible: appBridge && appBridge.fixedQualityCodecs.indexOf(appBridge.videoCodec) >= 0
                                        text: "Encoding Quality: Fixed by codec"
                                        color: Theme.textSecondary
                                        font.pixelSize: Theme.fontSizeSmall
                                    }

                                    AppCheckBox {
                                        label: "10-bit HDR Mode"
                                        checked: appBridge ? appBridge.videoHdrMode : false
                                        onToggled: (c) => { if (appBridge) appBridge.videoHdrMode = c }
                                    }

                                }
                            }
                        }
                    }
                }

                // Sticky Bottom Action Bar
                Rectangle {
                    id: actionBar
                    width: parent.width
                    height: 88
                    color: Theme.bgSurface
                    border.color: Theme.borderSubtle
                    border.width: 1

                    Column {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 6

                        Row {
                            width: parent.width
                            spacing: 8

                            AppButton {
                                text: "Preview"
                                iconName: "preview"
                                width: (parent.width - 16) / 3
                                buttonHeight: 30
                                enabled: appBridge ? appBridge.canPreview : false
                                onClicked: {
                                    if (appBridge) appBridge.renderPreviewAt(viewport.playheadMs)
                                }
                            }

                            AppButton {
                                text: "Reset"
                                iconName: "reset"
                                width: (parent.width - 16) / 3
                                buttonHeight: 30
                                onClicked: { if (appBridge) appBridge.resetTabSettings("neural-rendering") }
                            }

                            AppButton {
                                text: "Outputs"
                                iconName: "outputs_folder"
                                width: (parent.width - 16) / 3
                                buttonHeight: 30
                                onClicked: { if (appBridge) appBridge.openFolder("") }
                            }
                        }

                        AppButton {
                            text: appBridge && appBridge.canStop ? "Stop" : (root.isImage ? "Render Image(s)" : "Render Video(s)")
                            iconName: appBridge && appBridge.canStop ? "stop" : "start_render"
                            variant: appBridge && appBridge.canStop ? "danger" : "primary"
                            width: parent.width
                            buttonHeight: 34
                            enabled: appBridge ? (appBridge.canStop || (appBridge.operationState === "Idle" && appBridge.runtimeState === "Ready" && !appBridge.isLiveRunning)) : false
                            onClicked: {
                                if (appBridge) {
                                    if (appBridge.canStop) {
                                        appBridge.stopActiveBatch()
                                    } else {
                                        appBridge.requestActiveBatchExport()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
