class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.isRecording = false;

        // Listen for messages from the main thread
        this.port.onmessage = (event) => {
            if (event.data.command === 'START_RECORDING') {
                this.isRecording = true;
            } else if (event.data.command === 'STOP_RECORDING') {
                this.isRecording = false;
            }
        };
    }

    process(inputs, outputs, parameters) {
        // Process audio and convert to Int16Array
        if (this.isRecording && inputs[0] && inputs[0][0]) {
            const inputChannel = inputs[0][0];
            const buffer = new Int16Array(inputChannel.length);

            for (let i = 0; i < inputChannel.length; i++) {
                const s = Math.max(-1, Math.min(1, inputChannel[i]));
                buffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            this.port.postMessage({
                audioData: buffer,
                type: 'audio'
            });
        }

        return true;  // Keep processor running
    }
}

registerProcessor('audio-processor', AudioProcessor);