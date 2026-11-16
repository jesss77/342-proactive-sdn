"""Non-ML decisions only; every requested action still needs admission checks."""
import math


class Trigger:
    def __init__(self,policy,threshold=.85,confirmation_s=1.,horizon_s=2.):
        if policy not in ['fixed','reactive','early_warning']:
            raise ValueError('Unknown policy')
        self.policy=policy;self.threshold=threshold;self.confirmation_s=confirmation_s
        self.horizon_s=horizon_s;self.high_since=None;self.previous=None;self.fired=False

    def update(self,available,features,valid=True):
        u=features.get('utilization');slope=features.get('util_slope_2s')
        if (not valid or not all(isinstance(v,(int,float)) and math.isfinite(v)
                                for v in [available,u,slope])
            or (self.previous is not None and not 0<available-self.previous<=.5)):
            self.high_since=None;self.previous=None
            return None
        self.previous=available
        if self.fired or self.policy=='fixed': return None
        if u>=self.threshold:
            if self.high_since is None: self.high_since=available
        else: self.high_since=None
        reason=None
        if self.policy=='reactive' and self.high_since is not None and available-self.high_since>=self.confirmation_s:
            reason='observed_utilization_sustained'
        elif self.policy=='early_warning' and u>=.5 and slope>0 and u+self.horizon_s*slope>=self.threshold:
            reason='past_trend_forecast'
        return reason

    def mark_applied(self):
        self.fired=True
