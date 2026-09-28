// SDK sessions need an explicit join to the released web standard preset.
export const name = 'lab-sdk-standard';
export const inject = ['agents', 'agentPresets'];
export function apply(ctx) {
  ctx.on('agent/created', async ({ agent }) => {
    if (!ctx.agentPresets.composedPreset(agent.ctx)) {
      await ctx.agentPresets.select(agent, 'standard');
    }
  });
}
