#version 440
// 带贴图的道具（买来的饭盆、水盆）：和 prop.vert 一样不蒙皮、沿法线外推画轮廓线，多一条贴图坐标。改完跑 tools/build_shaders.sh 重新生成 .qsb。
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aUV;
layout(std140, binding = 0) uniform Scene {
    mat4 uViewProj;                        // 已经乘过 QRhi 的 clipSpaceCorrMatrix
    vec4 uLight;
};
layout(std140, binding = 1) uniform Item {
    mat4 uModel;
    vec4 uColor;                           // rgb 乘在贴图上，a 淡入淡出
    float uOutline;
    int uMode;                             // 0 本体；1 轮廓线
};
layout(location = 0) out vec3 vN;
layout(location = 1) out vec2 vUV;
void main() {
    vec3 p = aPos + aNormal * uOutline;
    vN = normalize(mat3(uModel) * aNormal);
    vUV = aUV;
    gl_Position = uViewProj * uModel * vec4(p, 1.0);
}
