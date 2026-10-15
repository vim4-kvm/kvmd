// SPDX-License-Identifier: GPL-3.0-or-later
"use strict";

// Annex B carries parameter sets in-band. Derive the RFC 6381 codec string
// from SPS profile_tier_level rather than assuming a resolution/encoder level.
export function hevcCodecFromAnnexB(data) {
	const startCode = (i) => (data[i] === 0 && data[i + 1] === 0
		? (data[i + 2] === 1 ? 3 : (data[i + 2] === 0 && data[i + 3] === 1 ? 4 : 0)) : 0);
	for (let i = 0; i + 5 < data.length; i++) {
		let size = startCode(i);
		if (!size || ((data[i + size] >> 1) & 63) !== 33) {
			continue;
		}
		let rbsp = [];
		let zeros = 0;
		for (let j = i + size + 2; j < data.length && !startCode(j); j++) {
			let byte = data[j];
			if (zeros >= 2 && byte === 3) {
				zeros = 0;
				continue;
			}
			rbsp.push(byte);
			zeros = (byte === 0 ? zeros + 1 : 0);
		}
		if (rbsp.length < 13) {
			throw new Error("Truncated HEVC SPS");
		}
		let profile = rbsp[1];
		let compatibility = 0;
		for (let bit = 0; bit < 32; bit++) {
			if (rbsp[2 + (bit >> 3)] & (1 << (7 - (bit & 7)))) {
				compatibility += 2 ** bit;
			}
		}
		let constraints = rbsp.slice(6, 12);
		while (constraints.length && constraints[constraints.length - 1] === 0) {
			constraints.pop();
		}
		let space = ["", "A", "B", "C"][profile >> 6];
		let tier = (profile & 32 ? "H" : "L");
		let suffix = constraints.map(byte => "." + byte.toString(16).toUpperCase()).join("");
		return `hev1.${space}${profile & 31}.${compatibility.toString(16).toUpperCase()}.${tier}${rbsp[12]}${suffix}`;
	}
	return null;
}
