# gst-webrtc
Streaming app based on rockchip 3588 ubuntu24


start simp.py https and signalling server after rockchip was able to get its ip address in local net
you can check it via $ip a
it will also generate actual webrtc.js.
sudo python3 simp.py --addr 192.168.88.28

go to https://192.168.88.28:8000
Status should change to 

make webrtc-sendrecv
launch it $./webrtc-sendrecv  --our-id=2 --server=wss://192.168.88.28:9000

go back to web page 
print 2 or other peer-id. 
click remote offer and Connect
Video stream should start
