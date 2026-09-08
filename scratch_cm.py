import joblib
import pandas as pd
from pathlib import Path
from sklearn.metrics import confusion_matrix
import sys
sys.path.insert(0, r"d:\Projects\Federated Learning\network_analysis")
from train_fused_model import load_fused_dataset, engineer_features

model = joblib.load(r"d:\Projects\Federated Learning\models\archive\fused_ids_model_global_R35.pkl")
scaler = joblib.load(r"d:\Projects\Federated Learning\models\scaler.pkl")
label_encoder = joblib.load(r"d:\Projects\Federated Learning\models\label_encoder.pkl")
feature_columns = joblib.load(r"d:\Projects\Federated Learning\models\feature_columns.pkl")

master_df = load_fused_dataset(Path(r"d:\Projects\Federated Learning\rpi\experiments\results"))
featured_df = engineer_features(master_df)

X_raw = featured_df.drop(columns=["AttackLabel"])
y_raw = featured_df["AttackLabel"]

for col in feature_columns:
    if col not in X_raw.columns:
        X_raw[col] = 0.0
X = X_raw[feature_columns]

y_encoded = label_encoder.transform(y_raw)
X_scaled = scaler.transform(X)

preds = model.predict(X_scaled)

labels = list(range(len(label_encoder.classes_)))
cm = confusion_matrix(y_encoded, preds, labels=labels)
cm_df = pd.DataFrame(cm, index=label_encoder.classes_, columns=label_encoder.classes_)
print(cm_df.to_string())
