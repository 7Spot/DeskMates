#version 440
// 狗：贴图 × 两档明暗；轮廓线是一个固定的深色。
layout(location = 0) in vec3 vN;
layout(location = 1) in vec2 vUV;
layout(std140, binding = 1) uniform Pass {
    vec4 uLight;
    float uOutline;
    int uMode;                             // 0 本体；1 轮廓线
    float uGain;                           // 贴图整体提亮多少倍（模型包的 brightness）：照着打了光来画的贴图，在这种不打光的画法下偏暗
};
layout(binding = 2) uniform sampler2D uTex;
layout(location = 0) out vec4 fragColor;
void main() {
    if (uMode == 1) { fragColor = vec4(0.16, 0.13, 0.11, 1.0); return; }
    vec4 c = texture(uTex, vUV);
    float d = max(dot(normalize(vN), normalize(uLight.xyz)), 0.0);
    float band = d > 0.35 ? 1.0 : 0.88;
    fragColor = vec4(min(c.rgb * uGain, vec3(1.0)) * band, 1.0);   // 先提亮、封顶，再分明暗：提到全白的地方暗面照样看得出
}
