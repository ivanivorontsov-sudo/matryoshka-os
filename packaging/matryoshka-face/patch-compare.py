import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
a = """	if (darkness > dark_threshold):
		dark_tries += 1
		continue
"""
b = """	if (darkness > dark_threshold):
		boosted = cv2.LUT(gsframe, gamma_lut)
		bhist = cv2.calcHist([boosted], [0], None, [8], [0, 256])
		if (bhist[0] / hist_total * 100) > dark_threshold:
			dark_tries += 1
			continue
		gsframe = boosted
		frame = cv2.LUT(frame, gamma_lut)
"""
c = """clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
"""
d = """clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
gamma_lut = np.array([min(255, int(((i / 255.0) ** 0.5) * 255)) for i in range(256)], dtype=np.uint8)
light_clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))


def light_fix(img):
	if img.ndim != 3:
		return light_clahe.apply(img)
	lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
	l, ca, cb = cv2.split(lab)
	return cv2.cvtColor(cv2.merge((light_clahe.apply(l), ca, cb)), cv2.COLOR_LAB2BGR)
"""
e = """		match_index = np.argmin(matches)
		match = matches[match_index]
"""
f = """		match_index = np.argmin(matches)
		match = matches[match_index]

		if not (0 < match < video_certainty):
			try:
				fixed = light_fix(frame)
				fixed_encoding = np.array(face_encoder.compute_face_descriptor(fixed, pose_predictor(fixed, fl), 1))
				fixed_matches = np.linalg.norm(encodings - fixed_encoding, axis=1)
				if 0 < np.min(fixed_matches) < match:
					match = np.min(fixed_matches)
			except Exception:
				pass
"""
for x, y in ((a, b), (c, d), (e, f)):
    if s.count(x) != 1:
        sys.exit("compare.py: pattern not found")
    s = s.replace(x, y)
open(p, "w", encoding="utf-8").write(s)
