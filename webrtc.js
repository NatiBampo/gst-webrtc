
    var ws_server = "192.168.88.28";
    var ws_port = "9000";
        
// Set this to override the automatic detection in websocketServerConnect()
//var ws_server = "192.168.88.18";
//var ws_port = "9000";
//remain
// Set this to use a specific peer id instead of a random one
var default_peer_id;
// Override with your own STUN servers if you want
var rtc_configuration = {iceServers: [{urls: "stun:stun.services.mozilla.com"},
                                      {urls: "stun:stun.l.google.com:19302"}]};
// The default constraints that will be attempted. Can be overriden by the user.
var default_constraints = {video: true, audio: true};

var connect_attempts = 0;
var peer_connection;
var send_channel;
var ws_conn;
// Promise for local stream after constraints are approved by the user
var local_stream_promise;

function setConnectButtonState(value) {
    document.getElementById("peer-connect-button").value = value;
}

function wantRemoteOfferer() {
   return document.getElementById("remote-offerer").checked;
}

function onConnectClicked() {
    if (document.getElementById("peer-connect-button").value == "Disconnect") {
        resetState();
        return;
    }

    var id = document.getElementById("peer-connect").value;
    if (id == "") {
        alert("Peer id must be filled out");
        return;
    }

    ws_conn.send("SESSION " + id);
    setConnectButtonState("Disconnect");
}

function getOurId() {
    return Math.floor(Math.random() * (9000 - 10) + 10).toString();
}

function resetState() {
    // This will call onServerClose()
    ws_conn.close();
}

function handleIncomingError(error) {
    setError("ERROR: " + error);
    resetState();
}

function getVideoElement() {
    return document.getElementById("stream");
}

function setStatus(text) {
    console.log(text);
    var span = document.getElementById("status")
    // Don't set the status if it already contains an error
    if (!span.classList.contains('error'))
        span.textContent = text;
}

function setError(text) {
    console.error(text);
    var span = document.getElementById("status")
    span.textContent = text;
    span.classList.add('error');
}

function resetVideo() {
    // Release the webcam and mic
    if (local_stream_promise)
        local_stream_promise.then(stream => {
            if (stream) {
                stream.getTracks().forEach(function (track) { track.stop(); });
            }
        });

    // Reset the video element and stop showing the last received frame
    var videoElement = getVideoElement();
    videoElement.pause();
    videoElement.src = "";
    videoElement.load();
}


function onIncomingSDP(sdp) {
    console.log("Received SDP:", sdp);
    peer_connection.setRemoteDescription(sdp).then(() => {
        console.log("Remote description set successfully");
        if (sdp.type == "offer") {
            console.log("Creating answer...");
            local_stream_promise.then((stream) => {
                peer_connection.createAnswer()
                    .then(onLocalDescription)
                    .catch((error) => {
                        console.error("Error creating answer:", error);
                    });
            }).catch((error) => {
                console.error("Error getting local stream:", error);
            });
        }
    }).catch((error) => {
        console.error("Error setting remote description:", error);
    });
}


function onLocalDescription(desc) {
    console.log("Got local description:", desc);
    peer_connection.setLocalDescription(desc).then(() => {
        console.log("Local description set successfully");
        var sdp = {'sdp': peer_connection.localDescription};
        ws_conn.send(JSON.stringify(sdp));
    }).catch((error) => {
        console.error("Error setting local description:", error);
    });
}

function generateOffer() {
    peer_connection.createOffer().then(onLocalDescription).catch(setError);
}


function onIncomingICE(ice) {
    console.log("Received ICE candidate:", ice);
    if (peer_connection.remoteDescription) {
        var candidate = new RTCIceCandidate(ice);
        peer_connection.addIceCandidate(candidate).catch((error) => {
            console.error("Error adding ICE candidate:", error);
        });
    } else {
        console.warn("Ignoring ICE candidate: No remote description set");
    }
}

function onServerMessage(event) {
    console.log("Received " + event.data);
    switch (event.data) {
        case "HELLO":
            setStatus("Registered with server, waiting for call");
            return;
        case "SESSION_OK":
            setStatus("Starting negotiation");
            if (wantRemoteOfferer()) {
                ws_conn.send("OFFER_REQUEST");
                setStatus("Sent OFFER_REQUEST, waiting for offer");
                return;
            }
            if (!peer_connection)
                createCall(null).then (generateOffer);
            return;
        case "OFFER_REQUEST":
            // The peer wants us to set up and then send an offer
            if (!peer_connection)
                createCall(null).then (generateOffer);
            return;
        default:
            if (event.data.startsWith("ERROR")) {
                handleIncomingError(event.data);
                return;
            }
            // Handle incoming JSON SDP and ICE messages
            try {
                msg = JSON.parse(event.data);
            } catch (e) {
                if (e instanceof SyntaxError) {
                    handleIncomingError("Error parsing incoming JSON: " + event.data);
                } else {
                    handleIncomingError("Unknown error parsing response: " + event.data);
                }
                return;
            }

            // Incoming JSON signals the beginning of a call
            if (!peer_connection)
                createCall(msg);

            if (msg.sdp != null) {
                onIncomingSDP(msg.sdp);
            } else if (msg.ice != null) {
                onIncomingICE(msg.ice);
            } else {
                handleIncomingError("Unknown incoming JSON: " + msg);
            }
    }
}

function onServerClose(event) {
    setStatus('Disconnected from server');
    resetVideo();

    if (peer_connection) {
        peer_connection.close();
        peer_connection = null;
    }

    // Reset after a second
    window.setTimeout(websocketServerConnect, 1000);
}

function onServerError(event) {
    setError("Unable to connect to server, did you add an exception for the certificate?")
    // Retry after 3 seconds
    window.setTimeout(websocketServerConnect, 3000);
}



function getLocalStream() {
    var getUserMedia = navigator.mediaDevices.getUserMedia ||
                      navigator.webkitGetUserMedia ||
                      navigator.mozGetUserMedia ||
                      navigator.msGetUserMedia;

    if (!getUserMedia) {
        setError("getUserMedia is not supported in this browser");
        return Promise.reject("getUserMedia not supported");
    }

    var constraints;
    var textarea = document.getElementById('constraints');
    try {
        constraints = JSON.parse(textarea.value);
    } catch (e) {
        console.error(e);
        setError('ERROR parsing constraints: ' + e.message + ', using default constraints');
        constraints = default_constraints;
    }
    console.log(JSON.stringify(constraints));

    return getUserMedia.call(navigator, constraints).catch((error) => {
        setError("Error accessing media devices: " + error.message);
        return Promise.reject(error);
    });
}


function websocketServerConnect() {
    connect_attempts++;
    if (connect_attempts > 3) {
        setError("Too many connection attempts, aborting. Refresh page to try again");
        return;
    }
    var span = document.getElementById("status");
    span.classList.remove('error');
    span.textContent = '';
    var textarea = document.getElementById('constraints');
    if (textarea.value == '')
        textarea.value = JSON.stringify(default_constraints);
    peer_id = default_peer_id || getOurId();
    ws_port = ws_port || '9000'; // Use the correct port
    ws_server = ws_server || "192.168.88.29"; // Use the server's IP address
    var ws_url = 'wss://' + ws_server + ':' + ws_port; // Use wss:// for secure WebSocket 'wss://'
    setStatus("Connecting to server " + ws_url);
    ws_conn = new WebSocket(ws_url);
    ws_conn.addEventListener('open', (event) => {
        document.getElementById("peer-id").textContent = peer_id;
        ws_conn.send('HELLO ' + peer_id);
        setStatus("Registering with server");
        setConnectButtonState("Connect");
    });
    ws_conn.addEventListener('error', onServerError);
    ws_conn.addEventListener('message', onServerMessage);
    ws_conn.addEventListener('close', onServerClose);
}

function onRemoteTrack(event) {
    if (getVideoElement().srcObject !== event.streams[0]) {
        console.log('Incoming stream');
        getVideoElement().srcObject = event.streams[0];
    }
}

function errorUserMediaHandler() {
    setError("Browser doesn't support getUserMedia!");
}

const handleDataChannelOpen = (event) =>{
    console.log("dataChannel.OnOpen", event);
};

const handleDataChannelMessageReceived = (event) =>{
    console.log("dataChannel.OnMessage:", event, event.data.type);

    setStatus("Received data channel message");
    if (typeof event.data === 'string' || event.data instanceof String) {
        console.log('Incoming string message: ' + event.data);
        textarea = document.getElementById("text")
        textarea.value = textarea.value + '\n' + event.data
    } else {
        console.log('Incoming data message');
    }
    send_channel.send("Hi! (from browser)");
};

const handleDataChannelError = (error) =>{
    console.log("dataChannel.OnError:", error);
};

const handleDataChannelClose = (event) =>{
    console.log("dataChannel.OnClose", event);
};

function onDataChannel(event) {
    setStatus("Data channel created");
    let receiveChannel = event.channel;
    receiveChannel.onopen = handleDataChannelOpen;
    receiveChannel.onmessage = handleDataChannelMessageReceived;
    receiveChannel.onerror = handleDataChannelError;
    receiveChannel.onclose = handleDataChannelClose;
}

function createCall(msg) {
    // Reset connection attempts because we connected successfully
    connect_attempts = 0;

    console.log('Creating RTCPeerConnection');

    peer_connection = new RTCPeerConnection(rtc_configuration);
    send_channel = peer_connection.createDataChannel('label', null);
    send_channel.onopen = handleDataChannelOpen;
    send_channel.onmessage = handleDataChannelMessageReceived;
    send_channel.onerror = handleDataChannelError;
    send_channel.onclose = handleDataChannelClose;
    peer_connection.ondatachannel = onDataChannel;
    peer_connection.ontrack = onRemoteTrack;
    /* Send our video/audio to the other peer */
    local_stream_promise = getLocalStream().then((stream) => {
        console.log('Adding local stream');
        peer_connection.addStream(stream);
        return stream;
    }).catch(setError);

    if (msg != null && !msg.sdp) {
        console.log("WARNING: First message wasn't an SDP message!?");
    }

    peer_connection.onicecandidate = (event) => {
        // We have a candidate, send it to the remote party with the
        // same uuid
        if (event.candidate == null) {
                console.log("ICE Candidate was null, done");
                return;
        }
        ws_conn.send(JSON.stringify({'ice': event.candidate}));
    };

    if (msg != null)
        setStatus("Created peer connection for call, waiting for SDP");

    setConnectButtonState("Disconnect");
    return local_stream_promise;
}

