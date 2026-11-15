#version 440
// 带贴图的道具：贴图 × 两档明暗（和 dog.frag 一样的分法、一样的轮廓线颜色），输出预乘 alpha。
layout(location = 0) in vec3 vN;
layout(location = 1) in vec2 vUV;
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
layout(binding = 2) uniform sampler2D uTex;
layout(location = 0) out vec4 fragColor;
void main() {
    if (uMode == 1) { fragColor = vec4(0.16, 0.13, 0.11, 1.0) * uColor.a; return; }
    vec3 c = texture(uTex, vUV).rgb * uColor.rgb;
    float d = max(dot(normalize(vN), normalize(uLight.xyz)), 0.0);
    float band = d > 0.35 ? 1.0 : 0.88;
    fragColor = vec4(c * band, 1.0) * uColor.a;
}
