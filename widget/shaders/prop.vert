#version 440
// 道具（盆 / 骨头 / 球）：不蒙皮，同样沿法线外推画轮廓线。
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(std140, binding = 0) uniform Scene {
    mat4 uViewProj;                        // 已经乘过 QRhi 的 clipSpaceCorrMatrix
    vec4 uLight;
};
layout(std140, binding = 1) uniform Item {
    mat4 uModel;
    vec4 uColor;                           // rgb 平涂的颜色，a 淡入淡出
    float uOutline;
    int uMode;                             // 0 本体；1 轮廓线
};
layout(location = 0) out vec3 vN;
void main() {
    vec3 p = aPos + aNormal * uOutline;
    vN = normalize(mat3(uModel) * aNormal);
    gl_Position = uViewProj * uModel * vec4(p, 1.0);
}
