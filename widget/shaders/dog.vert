#version 440
// 狗：蒙皮 + 沿法线外推（轮廓线用）。改完跑 tools/build_shaders.sh 重新生成 .qsb。
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aUV;
layout(location = 3) in vec4 aJoints;
layout(location = 4) in vec4 aWeights;
layout(location = 5) in float aOutlineW;   // 0 = 这个顶点不参与轮廓线
layout(std140, binding = 0) uniform Scene {
    mat4 uViewProj;                        // 已经乘过 QRhi 的 clipSpaceCorrMatrix
    mat4 uModel;
    mat4 uJoints[64];
};
layout(std140, binding = 1) uniform Pass {
    vec4 uLight;
    float uOutline;                        // 轮廓线外推多少米；画本体时是 0
    int uMode;                             // 0 本体；1 轮廓线
    float uGain;                           // 只有 dog.frag 用；两边的块要写得一样
};
layout(location = 0) out vec3 vN;
layout(location = 1) out vec2 vUV;
void main() {
    mat4 skin = aWeights.x * uJoints[int(aJoints.x)] + aWeights.y * uJoints[int(aJoints.y)]
              + aWeights.z * uJoints[int(aJoints.z)] + aWeights.w * uJoints[int(aJoints.w)];
    vec4 p = skin * vec4(aPos, 1.0);
    vec3 n = normalize(mat3(skin) * aNormal);
    p.xyz += n * uOutline * aOutlineW;
    vN = normalize(mat3(uModel) * n);
    vUV = aUV;
    gl_Position = uViewProj * uModel * p;
}
