import QtQuick
import QtMultimedia
import ".."
import "../controls"

Rectangle {
    id: root
    property var player: null
    property real frameRate: 30.0
    property bool muted: false
    // Fallback metadata from ffprobe (bridge.sourceDuration/sourceFps) so the
    // timeline never sticks at 00:00 when MediaPlayer hasn't loaded yet.
    property real fallbackDurationMs: 0
    property real fallbackFrameRate: 30.0
    // Emitted only for direct user timeline moves (scrub/step/jump), never
    // for programmatic seeks or playback ticks. The viewport debounces these
    // into scrub-realtime preview refreshes.
    signal userScrubbed(real posMs)
    // Pre-rendered timeline spans (seconds) painted green, e.g. Frame
    // Interpolation "Preview" clips: [{start: 12.0, end: 15.0, url: ...}].
    // Empty for every other workflow, which leaves the groove untouched.
    property var renderedRanges: []
    height: 50
    color: Theme.bgSurface
    border.color: Theme.borderSubtle
    border.width: 1

    readonly property real effectiveFps: frameRate > 0.01 ? frameRate : (fallbackFrameRate > 0.01 ? fallbackFrameRate : 30.0)
    readonly property real effectiveDuration: root.player && root.player.duration > 0 ? root.player.duration : fallbackDurationMs
    readonly property real effectivePosition: root.player ? Math.max(0, Math.min(effectiveDuration > 0 ? effectiveDuration : root.player.position, root.player.position)) : 0
    readonly property int currentFrame: Math.floor(effectivePosition * effectiveFps / 1000.0) + (effectiveDuration > 0 ? 1 : 0)
    readonly property int totalFrames: effectiveFps > 0 && effectiveDuration > 0 ? Math.max(1, Math.round(effectiveDuration * effectiveFps / 1000.0)) : 0

    function fmt(ms) {
        var total = Math.max(0, Math.floor(ms / 1000))
        var h = Math.floor(total / 3600)
        var m = Math.floor((total % 3600) / 60)
        var s = total % 60
        function pad(v) { return v < 10 ? "0" + v : "" + v }
        return h > 0 ? (h + ":" + pad(m) + ":" + pad(s)) : (pad(m) + ":" + pad(s))
    }
    function fmtPrecise(ms) {
        // Sub-second durations (single-frame previews) would floor to 00:00;
        // show tenths so a 41ms preview reads 00:00.0 instead of 00:00.
        if (ms < 1000) {
            var tenths = Math.max(0, Math.floor(ms / 100))
            return "00:00." + tenths
        }
        return fmt(ms)
    }
    function fmtDuration(ms) {
        return ms > 0 && ms < 1000 ? fmtPrecise(ms) : fmt(ms)
    }
    function stepFrames(frames) {
        if (!root.player) return
        var dur = root.player.duration > 0 ? root.player.duration : fallbackDurationMs
        if (!root.player.seekable && root.player.duration <= 0 && dur <= 0) return
        root.player.pause()
        var target = root.player.position + frames * 1000.0 / effectiveFps
        if (dur > 0) target = Math.max(0, Math.min(dur, target))
        else target = Math.max(0, target)
        root.player.position = target
        root.userScrubbed(target)
    }

    Row {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 7

        AppIconButton { iconSymbol: "|<"; tooltipText: "Start"; onClicked: { if (root.player) { root.player.pause(); root.player.position = 0; root.userScrubbed(0) } } }
        AppIconButton { iconSymbol: "<"; tooltipText: "Previous frame"; onClicked: root.stepFrames(-1) }
        AppButton {
            text: root.player && root.player.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
            width: 66; buttonHeight: 30
            onClicked: {
                if (!root.player) return
                if (root.player.playbackState === MediaPlayer.PlayingState) root.player.pause()
                else root.player.play()
            }
        }
        AppIconButton { iconSymbol: ">"; tooltipText: "Next frame"; onClicked: root.stepFrames(1) }

        Rectangle {
            width: Math.max(120, parent.width - 430)
            height: 14; radius: 7; anchors.verticalCenter: parent.verticalCenter; color: Theme.bgInput
            clip: true
            Rectangle {
                id: playheadFill
                readonly property bool atEnd: width >= parent.width || (root.effectiveDuration > 0 && root.effectivePosition >= root.effectiveDuration)
                width: parent.width * (root.effectiveDuration > 0 ? Math.max(0, Math.min(1, root.effectivePosition / root.effectiveDuration)) : 0)
                height: parent.height
                color: Theme.accent
                topLeftRadius: 7
                bottomLeftRadius: 7
                topRightRadius: atEnd ? 7 : 0
                bottomRightRadius: atEnd ? 7 : 0

                // Thin white vertical cutoff line at the moving head
                Rectangle {
                    id: playheadCutoff
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 1.5
                    color: "#FFFFFF"
                    visible: parent.width >= 2 && !playheadFill.atEnd
                }
            }
            // Green pre-rendered spans (FI "Preview"). Painted over the
            // accent playhead fill so a rendered span always reads green:
            // blue advances up to it, green holds while playing through it,
            // blue resumes after it. Exact position still shows in the label.
            Repeater {
                model: root.renderedRanges
                Rectangle {
                    required property var modelData
                    y: 0; height: parent.height; radius: 0; color: Theme.success
                    x: {
                        var dur = root.effectiveDuration
                        if (!(dur > 0)) return 0
                        var s = Math.max(0, Math.min(dur / 1000.0, modelData.start || 0))
                        return parent.width * (s / (dur / 1000.0))
                    }
                    width: {
                        var dur = root.effectiveDuration
                        if (!(dur > 0)) return 0
                        var total = dur / 1000.0
                        var s = Math.max(0, Math.min(total, modelData.start || 0))
                        var e = Math.max(0, Math.min(total, modelData.end || 0))
                        return Math.max(0, parent.width * ((e - s) / total))
                    }
                }
            }
            MouseArea {
                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                function seek(mouseX) {
                    var dur = root.player && root.player.duration > 0 ? root.player.duration : root.fallbackDurationMs
                    if (root.player && dur > 0) {
                        var target = Math.max(0, Math.min(dur, mouseX / width * dur))
                        root.player.position = target
                        root.userScrubbed(target)
                    }
                }
                onPressed: (mouse) => seek(mouse.x)
                onPositionChanged: (mouse) => { if (pressed) seek(mouse.x) }
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: {
                var pos = root.player ? root.player.position : 0
                var dur = root.player && root.player.duration > 0 ? root.player.duration : root.fallbackDurationMs
                var label = root.fmt(pos) + " / " + root.fmtDuration(dur)
                if (root.totalFrames > 0 && root.totalFrames < 100000)
                    label += "  -  f" + root.currentFrame + "/" + root.totalFrames
                else if (root.player && root.player.duration > 0 && root.player.duration < 1000)
                    label += "  -  1 frame"
                return label
            }
            color: Theme.textSecondary; font.family: Theme.monoFontFamily; font.pixelSize: Theme.fontSizeSmall
        }

        AppComboBox {
            width: 72; comboHeight: 30
            model: [{label:"0.5x",value:0.5},{label:"1x",value:1.0},{label:"1.5x",value:1.5},{label:"2x",value:2.0}]
            currentValue: root.player ? root.player.playbackRate : 1.0
            onActivated: (v) => { if (root.player) root.player.playbackRate = v }
        }
    }
}
