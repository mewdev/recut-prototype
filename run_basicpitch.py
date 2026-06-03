import pathlib, sys
audio = sys.argv[1]
out = sys.argv[2]
bp_model = pathlib.Path(__import__('basic_pitch').__file__).parent / 'saved_models/icassp_2022/nmp.onnx'
from basic_pitch.inference import predict
_, midi_data, _ = predict(audio, model_or_model_path=bp_model, minimum_note_length=180, onset_threshold=0.5, frame_threshold=0.3)
midi_data.write(out)
print(f'saved {out}')
