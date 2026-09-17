import QtQuick
import QtQuick.Dialogs
import ".."
import "../controls"

Rectangle {
    id: drawer
    property var appBridge: null
    property var queueModel: null
    property bool collapsed: false
    property bool hidden: false
    property int expandedHeight: appBridge ? appBridge.queueHeight : 190

    height: hidden ? 0 : (collapsed ? 36 : expandedHeight)
    visible: !hidden
    color: Theme.bgSurface
    border.color: Theme.borderSubtle
    border.width: 1

    Behavior on height { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutQuad } }

    Rectangle {
        id: header
        anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
        height: 36; color: "transparent"
        Row {
            anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 8
            Text { text: "Batch Queue"; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeLabel; font.weight: Font.DemiBold; color: Theme.textPrimary; anchors.verticalCenter: parent.verticalCenter }
            AppBadge { text: queueModel ? (queueModel.count + " files") : "0 files"; variant: queueModel && queueModel.count > 0 ? "accent" : "neutral"; anchors.verticalCenter: parent.verticalCenter }
            AppButton { text: "+ Files"; buttonHeight: 22; enabled: appBridge ? appBridge.canModifyQueue : true; onClicked: fileDialog.open() }
            AppButton { text: "+ Folder"; buttonHeight: 22; enabled: appBridge ? appBridge.canModifyQueue : true; onClicked: folderDialog.open() }
            AppButton { text: "Clear Done"; buttonHeight: 22; enabled: queueModel && queueModel.count > 0 && (appBridge ? appBridge.canModifyQueue : true); onClicked: { if (appBridge) appBridge.clearCompletedQueueItems() } }
            AppButton { text: "Clear All"; buttonHeight: 22; enabled: queueModel && queueModel.count > 0 && (appBridge ? appBridge.canModifyQueue : true); onClicked: { if (appBridge) appBridge.clearActiveQueue() } }
        }
        AppIconButton {
            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
            iconSymbol: drawer.collapsed ? "^" : "v"
            tooltipText: drawer.collapsed ? "Expand queue" : "Collapse queue"
            onClicked: drawer.collapsed = !drawer.collapsed
        }
        Rectangle { anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; height: 1; color: Theme.borderSubtle }
    }

    ListView {
        id: queueList
        anchors.top: header.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 8; orientation: ListView.Horizontal; spacing: 8; clip: true
        visible: !drawer.collapsed; model: drawer.queueModel

        delegate: Rectangle {
            id: itemCard
            required property int index
            required property string fileName
            required property string inputPath
            required property string outputPath
            required property string state
            required property real progress
            required property string detail
            required property real elapsedSeconds
            required property string inputDimensions
            required property string outputDimensions
            required property string thumbnailUrl
            required property bool selected

            width: Math.min(300, Math.max(250, queueList.width * 0.24))
            height: queueList.height - 2
            radius: Theme.radiusMedium
            color: selected ? Theme.bgSelected : (selectMouse.containsMouse ? Theme.bgCard : Theme.bgInput)
            border.color: selected ? Theme.accent : (selectMouse.containsMouse ? Theme.borderActive : Theme.borderSubtle)
            border.width: selected ? 1.5 : 1

            MouseArea {
                id: selectMouse; anchors.fill: parent; z: 0; hoverEnabled: true
                enabled: appBridge ? appBridge.canModifyQueue : true
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: { if (appBridge) appBridge.selectQueueItem(itemCard.index) }
            }

            Row {
                anchors.fill: parent; anchors.margins: 8; spacing: 8; z: 1
                Rectangle {
                    width: Math.min(90, parent.height - 4); height: parent.height - 4
                    radius: Theme.radiusSmall; color: Theme.bgBase; clip: true
                    Image { anchors.fill: parent; source: itemCard.thumbnailUrl; visible: itemCard.thumbnailUrl !== ""; fillMode: Image.PreserveAspectCrop; asynchronous: true; cache: false }
                    Text { anchors.centerIn: parent; visible: itemCard.thumbnailUrl === ""; text: "MEDIA"; color: Theme.textMuted; font.family: Theme.monoFontFamily; font.pixelSize: 10 }
                }

                Column {
                    width: parent.width - Math.min(90, parent.height - 4) - 8; height: parent.height; spacing: 4
                    Row {
                        width: parent.width; spacing: 6
                        Text { width: parent.width - removeBtn.width - 8; text: itemCard.fileName; elide: Text.ElideMiddle; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeLabel; font.weight: Font.DemiBold; color: Theme.textPrimary }
                        AppIconButton {
                            id: removeBtn; z: 20; iconSymbol: "x"; buttonSize: 20; showTooltip: false
                            visible: appBridge ? appBridge.canModifyQueue : true
                            onClicked: { if (appBridge) appBridge.removeQueueItem(itemCard.index) }
                        }
                    }
                    Row {
                        spacing: 6
                        AppBadge {
                            text: itemCard.state || "Queued"
                            variant: itemCard.state === "Completed" ? "success" : (itemCard.state === "Failed" ? "danger" : (itemCard.state === "Running" ? "accent" : (itemCard.state === "Cancelled" ? "warning" : "neutral")))
                        }
                        Text { text: itemCard.inputDimensions || ""; font.family: Theme.monoFontFamily; font.pixelSize: 10; color: Theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text { width: parent.width; text: itemCard.detail || (itemCard.outputDimensions ? ("Output " + itemCard.outputDimensions) : ""); elide: Text.ElideRight; font.family: Theme.monoFontFamily; font.pixelSize: 10; color: Theme.textMuted }
                    Rectangle {
                        width: parent.width; height: 5; radius: 2.5; color: Theme.bgBase
                        visible: itemCard.state === "Running" || itemCard.state === "Completed" || itemCard.progress > 0
                        Rectangle { height: parent.height; width: parent.width * Math.max(0, Math.min(1, itemCard.progress)); radius: 2.5; color: itemCard.state === "Completed" ? Theme.success : Theme.accent }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: itemCard.elapsedSeconds > 0 ? (itemCard.elapsedSeconds.toFixed(1) + "s") : ""; color: Theme.textMuted; font.family: Theme.monoFontFamily; font.pixelSize: 10 }
                        AppButton { text: "Reveal"; buttonHeight: 20; visible: itemCard.outputPath !== ""; onClicked: { if (appBridge) appBridge.openFolder(itemCard.outputPath) } }
                    }
                }
            }
        }

        Text {
            anchors.centerIn: parent; visible: !queueModel || queueModel.count === 0
            text: "Queue is empty. Add files, add a folder, or drop media into the viewport."
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeLabel; color: Theme.textMuted
        }
    }

    MouseArea {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: 5; z: 100; visible: !drawer.collapsed && !drawer.hidden; cursorShape: Qt.SizeVerCursor
        property real pressY: 0; property real startHeight: 0
        onPressed: (mouse) => { pressY = mouse.y; startHeight = drawer.expandedHeight }
        onPositionChanged: (mouse) => {
            if (!pressed) return
            var h = Math.max(120, Math.min(360, startHeight + pressY - mouse.y))
            drawer.expandedHeight = h
            if (drawer.appBridge) drawer.appBridge.queueHeight = Math.round(h)
        }
    }

    FolderDialog { id: folderDialog; title: "Add Folder to Batch"; onAccepted: { if (appBridge) appBridge.addFiles([selectedFolder.toString()]) } }
    FileDialog {
        id: fileDialog; title: "Add Files to Batch"; fileMode: FileDialog.OpenFiles; nameFilters: ["All Media Files (*.*)"]
        onAccepted: {
            if (!appBridge || selectedFiles.length === 0) return
            var urls = []; for (var i = 0; i < selectedFiles.length; i++) urls.push(selectedFiles[i].toString())
            appBridge.addFiles(urls)
        }
    }
}
