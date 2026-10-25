import os

# TensorFlow: sembunyikan pesan INFO/WARNING dari C++ selama latih/prediksi (galat tetap tampil). Harus
# diatur sebelum tensorflow diimpor. Pesan "oneDNN custom operations are on" saat import tetap muncul:
# di TensorFlow 2.21 pesan itu dicetak sebelum pengaturan log berlaku, dan hanya hilang jika oneDNN
# dimatikan (TF_ENABLE_ONEDNN_OPTS=0), yang tidak dilakukan karena mengubah hasil numerik.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
