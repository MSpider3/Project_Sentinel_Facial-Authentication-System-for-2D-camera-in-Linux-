# onnx_healthcheck.py
import onnx, onnxruntime as ort, numpy as np, sys

MODEL = "models/MiniFASNetV2.onnx"
print("Loading:", MODEL)
m = onnx.load(MODEL)
onnx.checker.check_model(m)
sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
inp = sess.get_inputs()[0].name
print("Input:", sess.get_inputs()[0].shape, "Output:", sess.get_outputs()[0].shape)

def run(x):
    y = sess.run(None, {inp: x})[0]
    return y

# feed three very different tensors
x0 = np.zeros((1,3,80,80), np.float32)             # all zeros
x1 = np.ones((1,3,80,80), np.float32)              # all ones
x2 = np.random.uniform(-1,1,(1,3,80,80)).astype(np.float32)  # random [-1,1]

for i,x in enumerate([x0,x1,x2],1):
    y = run(x)
    print(f"Case{i}: logits {y}, softmax {np.exp(y)/np.sum(np.exp(y))}")

# variance across many random inputs -> should NOT be ~0
ys=[]
for _ in range(32):
    xr = np.random.uniform(-1,1,(1,3,80,80)).astype(np.float32)
    ys.append(run(xr))
ys = np.vstack(ys)
print("Per-logit std across random inputs:", ys.std(axis=0))
