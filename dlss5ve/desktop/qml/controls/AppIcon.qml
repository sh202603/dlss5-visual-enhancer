import QtQuick
import QtQuick.Window
import ".."

Item {
    id: icon

    property string iconName: ""
    property int iconSize: 16
    property color color: Theme.textSecondary

    width: iconSize
    height: iconSize
    visible: iconName !== ""

    readonly property int rasterSize: {
        // Keep some source detail for high DPI scaling without shrinking a
        // very large texture into a tiny UI icon (which loses thin strokes).
        var needed = iconSize * Math.max(1, Screen.devicePixelRatio) * 1.5
        var sizes = [16, 20, 24, 32, 48, 64, 128, 256]
        for (var i = 0; i < sizes.length; ++i) {
            if (sizes[i] >= needed) return sizes[i]
        }
        return 256
    }

    Image {
        anchors.fill: parent
        source: icon.iconName === "" ? "" : "image://icons/" + icon.rasterSize + "/" + icon.iconName + "/" + icon.color.toString().replace("#", "")
        // The provider returns the chosen PNG at its native pixel size.
        // sourceSize is in device-independent units, so setting it to the PNG
        // size would make Qt upscale the request again on high DPI displays.
        fillMode: Image.PreserveAspectFit
        smooth: true
        // These icons are already downsampled from 256 px masters. Mipmaps
        // soften their one-pixel strokes at normal interface sizes.
        mipmap: false
    }
}
