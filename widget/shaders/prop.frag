#version 440
// 道具：平涂 × 两档明暗，输出预乘 alpha。
layout(location = 0) in vec3 vN;
layout(std140, binding = 0) uniform Scene {
    mat4 uViewProj;
    vec4 uLight;
};
layout(std140, binding = 1) uniform Item {
    mat4 uModel;
    vec4 uColor;
    float uOutline;
    int uMode;
};
layout(location = 0) out vec4 fragColor;
void main() {
    if (uMode == 1) { fragColor = vec4(0.16, 0.13, 0.11, 1.0) * uColor.a; return; }
    float d = max(dot(normalize(vN), normalize(uLight.xyz)), 0.0);
    float band = d > 0.35 ? 1.0 : 0.88;
    fragColor = vec4(uColor.rgb * band, 1.0) * uColor.a;
}
