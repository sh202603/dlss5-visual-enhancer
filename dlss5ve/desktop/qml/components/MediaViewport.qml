import QtQuick
import QtQuick.Window
import QtQuick.Controls as QQC2
import QtMultimedia
import ".."
import "../controls"

Rectangle {
    id: viewport
    property var appBridge: null
    property string viewMode: "split"
    property real zoomFactor: 1.0
    property real panX: 0
    property real panY: 0
    // Default to Input so a freshly finished single-frame preview never
    // hijacks the timeline (output is ~1 frame -> 00:00/00:00 + EOS black).
    property bool showVideoOutput: false
    // 2-Up comparison: input + output side by side with one shared timeline.
    property bool videoTwoUp: false
    property string playerError: ""
    // Hold-to-peek state: press-and-hold on the video shows the enhanced
    // preview frame; release restores the original. Pure momentary - the
    // Input/Output tabs remain the sticky switch.
    property bool peekActive: false
    property bool peekPrevShowOutput: false
    property bool peekWasPlaying: false

    color: Theme.bgBase
    clip: true
    focus: true

    readonly property bool hasInput: appBridge ? appBridge.previewInputUrl !== "" : false
    readonly property bool hasOutput: appBridge ? appBridge.hasOutputPreview : false
    readonly property bool isVideo: appBridge ? (appBridge.previewInputIsVideo || appBridge.previewOutputIsVideo) : false
    readonly property bool showingOutput: viewport.showVideoOutput && viewport.hasOutput && appBridge && appBridge.previewOutputIsVideo
    readonly property bool showingTwoUp: viewport.videoTwoUp && viewport.isVideo && viewport.hasOutput && appBridge && appBridge.previewOutputIsVideo
    // Output mirror gate: input masters the timeline in every layout while a
    // video preview exists; the output pane follows clamped to its duration.
    readonly property bool mirrorOutput: viewport.isVideo && viewport.hasOutput && appBridge && appBridge.previewOutputIsVideo
    // Scrub-realtime eligibility: Realtime on + an existing video preview, in
    // any layout. The transport always masters the input timeline (even on
    // the Output tab), so every scrub addresses input frames and refreshes
    // the preview at the settled playhead. The Preview button stays the
    // manual render path. Frame Interpolation is manual-only ("Preview"):
    // it never scrub-refreshes even when the global switch is on.
    readonly property bool isFITab: appBridge && appBridge.activeTab === "frame-interpolation"
    readonly property bool scrubRefreshEligible: appBridge && appBridge.autoPreviewEnabled && !viewport.isFITab && viewport.hasOutput && appBridge.previewOutputIsVideo
    // FI pre-rendered span containing timeline second sec, newest first wins
    // so re-rendered spans resolve to the latest clip. Null when outside all
    // green spans (or when ranges are unavailable).
    function fiRangeAt(sec) {
        if (!viewport.isFITab || !appBridge || !appBridge.previewRenderedRanges) return null
        var rs = appBridge.previewRenderedRanges
        for (var i = rs.length - 1; i >= 0; i--) {
            var r = rs[i]
            if (sec >= r.start && sec < r.end) return r
        }
        return null
    }
    // Range under the live playhead + the clip the output pane should show
    // on the FI tab. Swap discipline (this is what keeps playback smooth):
    // a VISIBLE player is never re-pointed. fiPinned is assigned only while
    // hidden (forward pre-warm), on settled pause/seek snaps, or in 2-Up
    // exact-follow. Boundary flips therefore land on an already-decoding
    // player: blue > green > blue = input-as-output > processed > input.
    property var fiPinned: null
    // Pre-warm horizon (seconds): while playing forward hidden, preload the
    // clip of the span starting inside this window. Tunable; ~1s covers a
    // cold demux+decode spin-up with margin, costing ~1s of double decode.
    property real fiLookaheadSec: 1.0
    // Last tick position: tells continuous play apart from seek jumps.
    property real fiLastPosMs: -1
    function fiPinTo(r) {
        var au = (viewport.fiPinned && viewport.fiPinned.url) ? viewport.fiPinned.url : ""
        var bu = (r && r.url) ? r.url : ""
        if (au !== bu) viewport.fiPinned = r
    }
    readonly property string fiOutputUrl: {
        if (!viewport.isFITab || !appBridge) return ""
        if (viewport.fiPinned && viewport.fiPinned.url) return viewport.fiPinned.url
        return appBridge.previewInputIsVideo ? appBridge.previewInputUrl : ""
    }
    readonly property var activePlayer: showingOutput ? outputPlayer : inputPlayer
    readonly property real playheadMs: viewport.isVideo ? inputPlayer.position : (activePlayer ? activePlayer.position : 0)
    readonly property real inputDurationMs: appBridge ? appBridge.sourceDuration * 1000.0 : 0
    readonly property real inputFps: appBridge && appBridge.sourceFps > 0 ? appBridge.sourceFps : 30.0
    readonly property bool inputReady: inputPlayer.duration > 0 && (inputPlayer.mediaStatus === MediaPlayer.LoadedMedia || inputPlayer.mediaStatus === MediaPlayer.BufferedMedia)
    readonly property bool outputReady: outputPlayer.duration > 0 && (outputPlayer.mediaStatus === MediaPlayer.LoadedMedia || outputPlayer.mediaStatus === MediaPlayer.BufferedMedia)
    readonly property bool activeReady: showingOutput ? outputReady : inputReady
    readonly property int sourceWidth: appBridge && appBridge.sourceWidth > 0 ? appBridge.sourceWidth : 1
    readonly property int sourceHeight: appBridge && appBridge.sourceHeight > 0 ? appBridge.sourceHeight : 1
    readonly property real fitScale: Math.max(0.0001, Math.min(canvas.width / sourceWidth, canvas.height / sourceHeight))
    readonly property real displayScale: fitScale * zoomFactor

    function resetPan() { panX = 0; panY = 0 }
    function fitToWindow() { zoomFactor = 1.0; resetPan() }
    function actualPixels() {
        var logicalScale = 1.0 / Math.max(1.0, Screen.devicePixelRatio)
        zoomFactor = Math.max(0.05, Math.min(32.0, logicalScale / fitScale))
        resetPan()
    }
    function clampPan() {
        var overX = Math.max(0, sourceWidth * displayScale - canvas.width) / 2
        var overY = Math.max(0, sourceHeight * displayScale - canvas.height) / 2
        panX = Math.max(-overX, Math.min(overX, panX))
        panY = Math.max(-overY, Math.min(overY, panY))
    }
    function changeZoom(multiplier) {
        zoomFactor = Math.max(0.05, Math.min(32.0, zoomFactor * multiplier))
        Qt.callLater(clampPan)
    }

    onSourceWidthChanged: fitToWindow()
    onSourceHeightChanged: fitToWindow()

    // Previews always land in place: the viewer stays on whichever tab
    // opened the render (Input, Output, or 2-Up). No tab is ever switched
    // programmatically - only the user (tabs) or a hold-release (peek) does.
    //
    // Same-frame sync needs no seeking: the transport masters the input
    // timeline in every layout, so Input/Output/2-Up always share one
    // playhead and the Input tab shows the scrubbed original by construction.

    AudioOutput { id: mediaAudio; volume: 0.8; muted: false }
    // Dedicated input player: transport/scrubbing always survives a preview.
    MediaPlayer {
        id: inputPlayer
        objectName: "inputPlayer"
        source: viewport.isVideo && appBridge && appBridge.previewInputIsVideo ? appBridge.previewInputUrl : ""
        audioOutput: mediaAudio
        videoOutput: inputSurface
        // Keep the last frame on screen instead of clearing to black at EOS.
        loops: MediaPlayer.Infinite
        property bool primePending: false
        onSourceChanged: {
            viewport.playerError = ""
            viewport.peekActive = false
            viewport.peekWasPlaying = false
            pause()
            // position assignment before media is loaded is ignored; the
            // priming handler below re-applies it once Loaded/Buffered.
            position = 0
            primePending = source !== ""
        }
        onMediaStatusChanged: (status) => {
            if ((status === MediaPlayer.LoadedMedia || status === MediaPlayer.BufferedMedia) && primePending) {
                primePending = false
                // Play-then-pause forces WMF to paint the first frame; a bare
                // pause()/position=0 leaves VideoOutput black on Windows.
                play()
                pause()
                position = 0
            }
            if (status === MediaPlayer.EndOfMedia && !viewport.showingOutput) {
                // Infinite loops already rewinds; keep position sane for UI.
            }
            if (status === MediaPlayer.InvalidMedia) {
                viewport.playerError = inputPlayer.errorString !== "" ? inputPlayer.errorString : "Unsupported video format."
            }
        }
        onErrorOccurred: (error, errorString) => {
            if (error !== MediaPlayer.NoError)
                viewport.playerError = errorString
            console.warn("inputPlayer error:", error, errorString, "source:", source)
        }
        onDurationChanged: (d) => { console.log("inputPlayer duration:", d, "source:", source) }
        // Output mirror: input is the master timeline in every layout; the
        // output follows clamped to its own (usually single-frame) duration.
        // One-directional so no feedback loop is possible. On the FI tab the
        // playhead is mapped into the green span's own clip instead, and
        // while playing the viewer auto-shows processed footage inside green
        // spans and the original outside (paused tabs stay manual; peek and
        // 2-Up are never overridden).
        onPositionChanged: (pos) => {
            if (viewport.isFITab && viewport.mirrorOutput) {
                var r = viewport.fiRangeAt(pos / 1000.0)
                var inputPlaying = inputPlayer.playbackState === MediaPlayer.PlayingState
                var jump = viewport.fiLastPosMs < 0 || Math.abs(pos - viewport.fiLastPosMs) > 800
                // Pinned clip went stale (ranges cleared by a settings tweak
                // mid-play): drop it so the next rule re-pins exact.
                if (viewport.fiPinned && viewport.fiPinned.url && appBridge && appBridge.previewRenderedRanges) {
                    var alive = false
                    var rs0 = appBridge.previewRenderedRanges
                    for (var k = 0; k < rs0.length; k++) {
                        if (rs0[k].url === viewport.fiPinned.url) { alive = true; break }
                    }
                    if (!alive) viewport.fiPinned = null
                }
                // Pinned range snapshot for this tick (null = blue / input).
                var pr = (viewport.fiPinned && viewport.fiPinned.start !== undefined) ? viewport.fiPinned : null
                var sec = pos / 1000.0
                // Pin discipline: a visible player is never re-pointed, so no
                // reload can ever stall visible playback — except rolling
                // forward across a span-to-span hop, where the pinned clip no
                // longer covers the playhead (steady spans never hit this).
                if (viewport.videoTwoUp) {
                    viewport.fiPinTo(r)
                } else if (r && viewport.showingOutput && (!pr || sec < pr.start || sec >= pr.end)) {
                    viewport.fiPinTo(r)
                } else if (!inputPlaying) {
                    viewport.fiPinTo(r)  // settled pause: exact inspection frame
                } else if (jump) {
                    // Seek while playing: prefer the lookahead span so a jump
                    // landing just before green doesn't reload twice in a row.
                    var wj = viewport.fiRangeAt(sec + viewport.fiLookaheadSec)
                    viewport.fiPinTo(wj ? wj : r)
                } else if (!viewport.showingOutput) {
                    var w = viewport.fiRangeAt(sec + viewport.fiLookaheadSec)
                    if (w) viewport.fiPinTo(w)  // hidden pre-warm only
                }
                // Pin may have moved above; refresh the snapshot for mirror
                // and pre-roll below.
                pr = (viewport.fiPinned && viewport.fiPinned.start !== undefined) ? viewport.fiPinned : null
                // Auto-show flip at the exact boundary (both panes hot).
                if (inputPlaying && !viewport.peekActive && !viewport.videoTwoUp) {
                    var want = (r !== null)
                    if (viewport.showVideoOutput !== want)
                        viewport.showVideoOutput = want
                }
                // Mirror + run state. The mirror follows the PINNED clip (not
                // just the current span): during approach the future clip is
                // held at its first frame, so the entry flip lands on a hot,
                // in-sync player instead of cold-seeking from the clip end
                // (that cold seek was the ~200ms entry flicker). Output always
                // carries timeline footage, so it simply tracks the input;
                // hidden + unneeded decode is shed by pausing.
                if (outputPlayer.duration > 0) {
                    var base = pr ? (pos - pr.start * 1000.0) : pos
                    if (base < 0) {
                        // Approach hold: first frame stays painted. Seek back
                        // only while parked — never yank a pre-rolling clip
                        // mid spin-up (it free-runs its final stretch).
                        if (outputPlayer.playbackState !== MediaPlayer.PlayingState
                                && Math.abs(outputPlayer.position) > 120)
                            outputPlayer.position = 0
                    } else {
                        var tgt = Math.max(0, Math.min(outputPlayer.duration, base))
                        if (Math.abs(outputPlayer.position - tgt) > 120)
                            outputPlayer.position = tgt
                    }
                }
                // Pre-roll: run the hidden clip through the final stretch
                // before its span so entry needs zero spin-up. Window matches
                // the mirror deadband, so free-run drift never trips a
                // correction seek; the clip was primed during pre-warm, so
                // play() resumes in a frame or two.
                var distStart = pr ? (pr.start * 1000.0 - pos) : 1e18
                var preRoll = inputPlaying && !viewport.showingOutput && !viewport.videoTwoUp
                    && pr && distStart >= 0 && distStart < 120
                var shouldRun = inputPlaying && (viewport.showingOutput || viewport.showingTwoUp || preRoll)
                if (shouldRun && outputPlayer.playbackState !== MediaPlayer.PlayingState)
                    outputPlayer.play()
                else if (!shouldRun && outputPlayer.playbackState === MediaPlayer.PlayingState)
                    outputPlayer.pause()
                viewport.fiLastPosMs = pos
                return
            }
            if (!viewport.mirrorOutput || outputPlayer.duration <= 0) return
            var target = Math.max(0, Math.min(outputPlayer.duration, pos))
            if (Math.abs(outputPlayer.position - target) > 120)
                outputPlayer.position = target
        }
        onPlaybackStateChanged: (state) => {
            // Parked: remember the frame so realtime auto-renders (settings
            // tweaks, menu action) preview it instead of frame 1. Independent
            // of mirroring so it also works before any output exists.
            if (state !== MediaPlayer.PlayingState && appBridge && viewport.isVideo)
                appBridge.notePlayheadMs(inputPlayer.position)
            if (!viewport.mirrorOutput) return
            // Output always carries timeline-meaningful footage (on FI the
            // original outside green, the range clip inside), so it simply
            // runs/pauses with the input on every tab. On FI pause the pin
            // snaps exact (ticks don't fire while paused, so the Output tab
            // inspects the settled frame, not a stale pre-warmed clip).
            if (viewport.isFITab && state !== MediaPlayer.PlayingState)
                viewport.fiPinTo(viewport.fiRangeAt(viewport.playheadMs / 1000.0))
            if (state === MediaPlayer.PlayingState) outputPlayer.play()
            else outputPlayer.pause()
        }
    }
        // Dedicated preview-output player (usually a single enhanced frame).
        // Independent from inputPlayer so stepping/scrubbing the source is never
        // clamped to the 1-frame preview duration. On the FI tab the source
        // follows the pinned span (pre-warmed up to fiLookaheadSec ahead while
        // hidden, snapped exact on pause/seek); everywhere else it is the
        // latest preview output. FI range clips play once (loops: 1) so a span
        // never replays at its end — playback continues with the original.
        MediaPlayer {
        id: outputPlayer
        objectName: "outputPlayer"
        source: viewport.isVideo && appBridge ? (viewport.isFITab ? viewport.fiOutputUrl : (appBridge.previewOutputIsVideo ? appBridge.previewOutputUrl : "")) : ""
        audioOutput: mediaAudio
        videoOutput: outputSurface
        loops: viewport.isFITab ? 1 : MediaPlayer.Infinite
        property bool primePending: false
        onSourceChanged: {
            pause()
            position = 0
            primePending = source !== ""
        }
        onMediaStatusChanged: (status) => {
            if ((status === MediaPlayer.LoadedMedia || status === MediaPlayer.BufferedMedia) && primePending) {
                primePending = false
                play()
                pause()
                position = 0
            }
            if (status === MediaPlayer.InvalidMedia && viewport.showingOutput) {
                viewport.playerError = errorString !== "" ? errorString : "Preview output is not playable."
            }
        }
        onErrorOccurred: (error, errorString) => {
            if (error !== MediaPlayer.NoError && viewport.showingOutput)
                viewport.playerError = errorString
            console.warn("outputPlayer error:", error, errorString, "source:", source)
        }
    }

    Keys.onPressed: (event) => {
        var transportPlayer = videoTransport.player
        if (viewport.isVideo && videoTransport.visible && transportPlayer) {
            if (event.key === Qt.Key_Space) {
                if (transportPlayer.playbackState === MediaPlayer.PlayingState) transportPlayer.pause(); else transportPlayer.play()
                event.accepted = true
            } else if (event.key === Qt.Key_Left) { videoTransport.stepFrames(-1); event.accepted = true }
            else if (event.key === Qt.Key_Right) { videoTransport.stepFrames(1); event.accepted = true }
        } else {
            if (event.key === Qt.Key_0) { viewport.fitToWindow(); event.accepted = true }
            if (event.key === Qt.Key_1) { viewport.actualPixels(); event.accepted = true }
        }
    }

    Rectangle {
        id: toolbar
        z: 20
        anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
        height: 42; visible: viewport.hasInput
        color: "#E014171D"; border.color: Theme.borderSubtle

        Row {
            anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 8
            AppSegmentedControl {
                visible: !viewport.isVideo
                width: 250
                model: [{label:"Split",value:"split"},{label:"2-Up",value:"sideBySide"},{label:"Output",value:"single"}]
                currentValue: viewport.viewMode
                onActivated: (v) => viewport.viewMode = v
            }
            AppSegmentedControl {
                visible: viewport.isVideo && viewport.hasOutput && appBridge && appBridge.previewOutputIsVideo
                width: 225
                model: [{label:"Input",value:"input"},{label:"Output",value:"output"},{label:"2-Up",value:"twoup"}]
                currentValue: viewport.videoTwoUp ? "twoup" : (viewport.showVideoOutput ? "output" : "input")
                onActivated: (v) => {
                    if (v === "twoup") {
                        viewport.videoTwoUp = true
                    } else {
                        viewport.videoTwoUp = false
                        viewport.showVideoOutput = (v === "output")
                    }
                }
            }
            Text {
                width: Math.max(120, toolbar.width - 620)
                text: appBridge ? appBridge.inputInfoText + (appBridge.hasOutputPreview ? "  ->  " + appBridge.outputInfoText : "") : ""
                elide: Text.ElideMiddle; color: Theme.textSecondary
                font.family: Theme.monoFontFamily; font.pixelSize: Theme.fontSizeSmall
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Row {
            visible: !viewport.isVideo
            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 6
            AppButton { text: "Fit"; buttonHeight: 26; width: 48; onClicked: viewport.fitToWindow() }
            AppButton { text: "100%"; buttonHeight: 26; width: 54; onClicked: viewport.actualPixels() }
            Text { text: Math.round(viewport.displayScale * Math.max(1.0, Screen.devicePixelRatio) * 100) + "%"; color: Theme.textPrimary; font.family: Theme.monoFontFamily; anchors.verticalCenter: parent.verticalCenter }
            AppIconButton { iconSymbol: "-"; showTooltip: false; onClicked: viewport.changeZoom(0.8) }
            AppIconButton { iconSymbol: "+"; showTooltip: false; onClicked: viewport.changeZoom(1.25) }
            AppIconButton {
                iconSymbol: appBridge && appBridge.focusPreview ? "[X]" : "[ ]"
                showTooltip: false
                onClicked: { if (appBridge) appBridge.focusPreview = !appBridge.focusPreview }
            }
        }
    }

    DropZone { anchors.fill: parent; visible: !viewport.hasInput; appBridge: viewport.appBridge }

    Item {
        id: canvas
        anchors.top: toolbar.bottom; anchors.left: parent.left; anchors.right: parent.right
        anchors.bottom: videoTransport.visible ? videoTransport.top : parent.bottom
        visible: viewport.hasInput; clip: true

        // ffmpeg-extracted poster behind the INPUT surface only: guarantees a
        // visible first frame even while WMF is loading or on decode error.
        // Never shown under Output/2-Up panes - a frameless VideoOutput is
        // transparent, so the fullscreen input poster would bleed through as
        // a "big image under" artifact on every preview swap (~100 ms).
        Image {
            id: videoPoster
            objectName: "videoPoster"
            anchors.fill: parent
            visible: viewport.isVideo && !viewport.showingOutput && !viewport.showingTwoUp && !viewport.inputReady
            source: appBridge ? appBridge.previewPosterUrl : ""
            fillMode: Image.PreserveAspectFit; cache: false; asynchronous: true; smooth: true
        }

        // Single-pane surfaces double as 2-Up panes: only their geometry
        // changes, so players never re-link outputs (no repaint stall).
        VideoOutput {
            id: inputSurface
            objectName: "inputSurface"
            anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.left: parent.left
            width: viewport.showingTwoUp ? (parent.width - 4) / 2 : parent.width
            visible: viewport.isVideo && (!viewport.showingOutput || viewport.showingTwoUp)
            fillMode: VideoOutput.PreserveAspectFit
        }
        VideoOutput {
            id: outputSurface
            objectName: "outputSurface"
            anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right
            width: viewport.showingTwoUp ? (parent.width - 4) / 2 : parent.width
            visible: viewport.isVideo && (viewport.showingOutput || viewport.showingTwoUp)
            fillMode: VideoOutput.PreserveAspectFit
        }

        // 2-Up comparison chrome: pane badges + output loading placeholder.
        // Mirrors the image side-by-side pattern.
        AppBadge {
            anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 10
            visible: viewport.showingTwoUp; text: "INPUT"
        }
        AppBadge {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 10
            visible: viewport.showingTwoUp
            text: viewport.outputReady ? ("OUTPUT" + (appBridge && appBridge.previewSourceFrame > 0 ? " f" + appBridge.previewSourceFrame : "")) : "NO OUTPUT"
            variant: viewport.outputReady ? "accent" : "neutral"
        }
        Text {
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            width: (parent.width - 4) / 2; horizontalAlignment: Text.AlignHCenter
            visible: viewport.showingTwoUp && !viewport.outputReady
            text: "Loading preview..."
            color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
        }

        // Single-Output swap veil: the output surface is transparent until the
        // new clip primes, so dim it with a label instead of flashing the
        // (wrong) input poster underneath.
        Rectangle {
            anchors.fill: parent; z: 2
            objectName: "outputLoadingVeil"
            visible: viewport.isVideo && viewport.showingOutput && !viewport.showingTwoUp && !viewport.outputReady
            color: "#AA0B0D12"
            Text {
                anchors.centerIn: parent
                text: "Loading preview..."
                color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
            }
        }

        // Hold-to-peek: press-and-hold on the video shows the enhanced
        // preview frame while held, release restores the original input.
        // Frozen (both players paused) for frame-accurate A/B comparison.
        MouseArea {
            id: peekArea
            anchors.fill: parent
            z: 4
            visible: viewport.isVideo && viewport.hasOutput && appBridge && appBridge.previewOutputIsVideo && !viewport.showingTwoUp
            acceptedButtons: Qt.LeftButton
            hoverEnabled: true
            cursorShape: containsMouse ? Qt.PointingHandCursor : Qt.ArrowCursor
            onPressed: (mouse) => {
                viewport.peekPrevShowOutput = viewport.showVideoOutput
                viewport.peekWasPlaying = viewport.activePlayer && viewport.activePlayer.playbackState === MediaPlayer.PlayingState
                inputPlayer.pause()
                outputPlayer.pause()
                viewport.showVideoOutput = true
                viewport.peekActive = true
                viewport.forceActiveFocus()
                mouse.accepted = true
            }
            function endPeek(restorePlayback) {
                if (!viewport.peekActive) return
                viewport.peekActive = false
                viewport.showVideoOutput = viewport.peekPrevShowOutput
                if (restorePlayback && viewport.peekWasPlaying && viewport.activePlayer)
                    viewport.activePlayer.play()
                viewport.peekWasPlaying = false
            }
            onReleased: endPeek(true)
            onCanceled: endPeek(true)
        }

        // Peek badge + highlight while held.
        Rectangle {
            z: 6
            anchors.top: parent.top; anchors.topMargin: 10
            anchors.horizontalCenter: parent.horizontalCenter
            visible: viewport.peekActive && viewport.showingOutput
            width: peekLabel.width + 24; height: 28; radius: 14
            color: "#CC14B8A6"; border.color: Theme.accent; border.width: 1
            Text {
                id: peekLabel
                anchors.centerIn: parent
                text: "PREVIEW"
                color: "white"; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; font.bold: true
            }
        }
        Rectangle {
            anchors.fill: parent; z: 3
            visible: viewport.peekActive && viewport.showingOutput
            color: "transparent"; border.color: Theme.accent; border.width: 2
        }

        // Decode-error overlay: poster stays visible underneath.
        Rectangle {
            anchors.fill: parent
            visible: viewport.isVideo && viewport.playerError !== "" && !viewport.activeReady
            color: "#AA000000"; z: 5
            Text {
                anchors.centerIn: parent; width: parent.width - 40
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                text: "Video cannot be played natively:\n" + viewport.playerError + "\nPoster frame shown. Scrub with < > or open the file externally."
                color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
            }
        }

        Item {
            id: imageLayer
            anchors.fill: parent
            visible: !viewport.isVideo && viewport.viewMode !== "sideBySide"

            Item {
                id: mediaFrame
                z: 1
                width: viewport.sourceWidth; height: viewport.sourceHeight
                transformOrigin: Item.TopLeft
                scale: viewport.displayScale
                x: (imageLayer.width - width * scale) / 2 + viewport.panX
                y: (imageLayer.height - height * scale) / 2 + viewport.panY

                Image {
                    anchors.fill: parent
                    source: appBridge ? appBridge.previewInputUrl : ""
                    fillMode: Image.Stretch; cache: false; asynchronous: true; smooth: true
                }

                Item {
                    anchors.fill: parent
                    visible: viewport.hasOutput && viewport.viewMode === "split"
                    clip: true
                    Item {
                        x: parent.width * (appBridge ? appBridge.splitPosition : 0.5)
                        width: parent.width - x; height: parent.height; clip: true
                        Image {
                            x: -parent.x; width: mediaFrame.width; height: mediaFrame.height
                            source: appBridge ? appBridge.previewOutputUrl : ""
                            fillMode: Image.Stretch; cache: false; smooth: true
                        }
                    }
                    Rectangle {
                        id: divider
                        x: parent.width * (appBridge ? appBridge.splitPosition : 0.5) - 0.75 / Math.max(0.001, mediaFrame.scale)
                        width: 1.5 / Math.max(0.001, mediaFrame.scale); height: parent.height; color: Theme.accent; z: 4
                        MouseArea {
                            id: splitMouse
                            anchors.fill: parent; anchors.margins: -10 / Math.max(0.001, mediaFrame.scale); cursorShape: Qt.SplitHCursor; hoverEnabled: true
                            function setSplit(mx, my) {
                                if (!appBridge) return
                                var p = splitMouse.mapToItem(divider.parent, mx, my)
                                var w = divider.parent.width
                                if (w > 0) appBridge.splitPosition = Math.max(0.02, Math.min(0.98, p.x / w))
                            }
                            onPressed: (m) => setSplit(m.x, m.y)
                            onPositionChanged: (m) => {
                                if (pressed) setSplit(m.x, m.y)
                            }
                        }
                    }
                }

                Image {
                    anchors.fill: parent
                    visible: viewport.hasOutput && viewport.viewMode === "single"
                    source: appBridge ? appBridge.previewOutputUrl : ""
                    fillMode: Image.Stretch; cache: false; smooth: true
                }
            }

            MouseArea {
                id: panArea
                z: 0
                anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                property real pressX: 0; property real pressY: 0; property real originPanX: 0; property real originPanY: 0
                onPressed: (mouse) => { pressX = mouse.x; pressY = mouse.y; originPanX = viewport.panX; originPanY = viewport.panY; viewport.forceActiveFocus() }
                onPositionChanged: (mouse) => {
                    if (!pressed) return
                    viewport.panX = originPanX + mouse.x - pressX
                    viewport.panY = originPanY + mouse.y - pressY
                    viewport.clampPan()
                }
                onDoubleClicked: viewport.fitToWindow()
                onWheel: (wheel) => { viewport.changeZoom(wheel.angleDelta.y > 0 ? 1.12 : 0.89); wheel.accepted = true }
            }
        }

        Row {
            anchors.fill: parent; spacing: 4
            visible: !viewport.isVideo && viewport.viewMode === "sideBySide"
            Rectangle {
                width: (parent.width - 4) / 2; height: parent.height; color: Theme.bgBase
                Image { anchors.fill: parent; anchors.margins: 4; source: appBridge ? appBridge.previewInputUrl : ""; fillMode: Image.PreserveAspectFit; cache: false }
                AppBadge { anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 10; text: "INPUT" }
            }
            Rectangle {
                width: (parent.width - 4) / 2; height: parent.height; color: Theme.bgBase
                Image { anchors.fill: parent; anchors.margins: 4; source: appBridge ? appBridge.previewOutputUrl : ""; fillMode: Image.PreserveAspectFit; cache: false }
                AppBadge { anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 10; text: viewport.hasOutput ? "OUTPUT" : "NO OUTPUT"; variant: viewport.hasOutput ? "accent" : "neutral" }
            }
        }

        // Right-click catcher for the preview context menu. RightButton ONLY
        // and stacked BELOW the interactive layers, so hover/cursor behavior
        // (split divider, pan hand, peek pointer) is untouched: none of the
        // layers above accept RightButton, so those presses fall through to
        // here. Inert when empty so DropZone keeps its own behavior.
        MouseArea {
            id: rightClickLayer
            anchors.fill: parent
            z: -1
            enabled: viewport.hasInput
            acceptedButtons: Qt.RightButton
            hoverEnabled: false
            onPressed: (mouse) => {
                if (mouse.button === Qt.RightButton && viewport.hasInput) {
                    previewMenu.popup(rightClickLayer, mouse.x, mouse.y)
                    mouse.accepted = true
                }
            }
        }
    }

    VideoTransportBar {
        id: videoTransport
        objectName: "videoTransport"
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        visible: viewport.hasInput && viewport.isVideo
        // The transport always masters the input timeline (even on the Output
        // tab); the output pane mirrors it. Scrubbing anywhere addresses
        // input frames, so refreshes can never clobber the preview.
        player: inputPlayer
        frameRate: viewport.inputFps
        fallbackDurationMs: viewport.inputDurationMs
        fallbackFrameRate: viewport.inputFps
        // Green pre-rendered spans (FI "Preview" only; [] elsewhere).
        renderedRanges: viewport.isFITab && appBridge ? appBridge.previewRenderedRanges : []
        onUserScrubbed: (posMs) => {
            appBridge.notePlayheadMs(posMs)
            if (viewport.scrubRefreshEligible) appBridge.schedulePreviewAt(posMs)
        }
    }

    // Status readout, bottom-left. Idle "Ready." is hidden when empty;
    // any other status still shows, and everything shows once loaded.
    Row {
        id: statusOverlay
        z: 30
        visible: viewport.hasInput || (appBridge && appBridge.statusMessage !== "Ready.")
        anchors.left: parent.left; anchors.leftMargin: 10
        anchors.bottom: videoTransport.visible ? videoTransport.top : parent.bottom
        anchors.bottomMargin: 8
        spacing: 8
        Rectangle {
            width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
            color: {
                if (!appBridge) return Theme.textMuted
                if (appBridge.runtimeState === "Failed") return Theme.danger
                if (appBridge.operationState === "LiveRunning") return Theme.danger
                if (appBridge.isProcessing) return Theme.accent
                if (appBridge.runtimeState === "Initializing") return Theme.warning
                return Theme.success
            }
        }
        Text {
            width: Math.min(520, viewport.width * 0.6); elide: Text.ElideRight
            text: appBridge ? appBridge.statusMessage : "Ready."
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter
        }
    }

    Rectangle {
        anchors.centerIn: parent
        visible: appBridge && (appBridge.operationState === "PreviewPreparing" || appBridge.operationState === "PreviewRunning" || appBridge.operationState === "LoadingMetadata")
        width: Math.min(parent.width - 40, 300); height: 64; radius: Theme.radiusLarge
        color: Theme.bgSurface; border.color: Theme.accent
        Text { anchors.centerIn: parent; text: appBridge ? appBridge.statusMessage : "Working..."; color: Theme.textPrimary; font.family: Theme.fontFamily; elide: Text.ElideRight; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter }
    }

    // Preview right-click menu: Clear single / Clear all / Show in Explorer
    // (current selection only). Compact dark styling hugging items closely on all 4 sides.
    // Clear actions honor canModifyQueue (dimmed while busy); Show in Explorer only needs loaded input.
    QQC2.Menu {
        id: previewMenu
        leftInset: 0
        rightInset: 0
        topInset: 0
        bottomInset: 0
        topPadding: 3
        bottomPadding: 3
        leftPadding: 3
        rightPadding: 3
        spacing: 1

        TextMetrics {
            id: previewFontMetrics
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
            text: "Show in Explorer"
        }

        background: Rectangle {
            color: Theme.bgSurface
            border.color: Theme.borderDefault
            border.width: 1
            radius: Theme.radiusSmall
            implicitWidth: Math.max(124, Math.ceil(previewFontMetrics.width) + 24)
        }

        delegate: QQC2.MenuItem {
            id: previewMi
            implicitHeight: 25
            leftPadding: 10
            rightPadding: 10
            indicator: null
            contentItem: Text {
                text: previewMi.text
                color: !previewMi.enabled ? Theme.textMuted : (previewMi.highlighted ? Theme.textPrimary : Theme.textSecondary)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.weight: Font.Normal
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                color: previewMi.highlighted && previewMi.enabled ? Theme.bgHover : "transparent"
                radius: 3
            }
        }

        QQC2.MenuItem {
            implicitHeight: 25
            text: viewport.isVideo ? "Clear video" : "Clear image"
            enabled: viewport.hasInput && appBridge && appBridge.canModifyQueue
            onTriggered: { if (appBridge) appBridge.clearSelectedPreviewItem() }
        }
        QQC2.MenuItem {
            implicitHeight: 25
            text: "Clear all"
            enabled: viewport.hasInput && appBridge && appBridge.canModifyQueue
            onTriggered: { if (appBridge) appBridge.clearActiveQueue() }
        }
        QQC2.MenuItem {
            implicitHeight: 25
            text: "Show in Explorer"
            enabled: viewport.hasInput && appBridge
            onTriggered: { if (appBridge) appBridge.showSelectedInExplorer() }
        }
    }
}
