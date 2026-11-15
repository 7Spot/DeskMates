#version 440
// 接触阴影：一个边缘渐隐的黑椭圆。
layout(location = 0) in vec2 vUV;
layout(std140, binding = 0) uniform Shadow {
    vec2 uSize;                            // 画的这一块有多少像素
    vec2 uCenter;                          // 椭圆中心（像素，原点左下）
    vec2 uRadius;
    float uAlpha;
};
layout(location = 0) out vec4 fragColor;
void main() {
    float d = length((vUV * uSize - uCenter) / uRadius);
    float a = uAlpha * (1.0 - smoothstep(0.25, 1.0, d));
    fragColor = vec4(0.0, 0.0, 0.0, a);    // 预乘：黑色
}
